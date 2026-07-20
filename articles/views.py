import json
import urllib.request
import urllib.parse
import re
import random
import datetime
from google import genai
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import FieldError
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.db.models import Q, Case, When, Value, IntegerField
from django.urls import reverse

from .forms import ArticleForm
from .models import Article, Book, Chapter, Section, Cart, CartItem, Order, OrderItem
from .emails import send_order_confirmation
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

import os
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))

# ==========================================
# פונקציות לוח שנה עברי (פרשה, הפטרה, מועדים)
# ==========================================
def translate_haftarah(text):
    if not text: return ""
    books = {
        'Genesis': 'בראשית', 'Exodus': 'שמות', 'Leviticus': 'ויקרא', 'Numbers': 'במדבר', 'Deuteronomy': 'דברים',
        'Joshua': 'יהושע', 'Judges': 'שופטים', 'I Samuel': 'שמואל א', 'II Samuel': 'שמואל ב', 'Samuel': 'שמואל',
        'I Kings': 'מלכים א', 'II Kings': 'מלכים ב', 'Kings': 'מלכים', 'Isaiah': 'ישעיהו', 'Jeremiah': 'ירמיהו',
        'Ezekiel': 'יחזקאל', 'Hosea': 'הושע', 'Joel': 'יואל', 'Amos': 'עמוס', 'Obadiah': 'עובדיה', 'Jonah': 'יונה',
        'Micah': 'מיכה', 'Nahum': 'נחום', 'Habakkuk': 'חבקוק', 'Zephaniah': 'צפניה', 'Haggai': 'חגי', 
        'Zechariah': 'זכריה', 'Malachi': 'מלאכי', 'Psalms': 'תהילים', 'Proverbs': 'משלי', 'Job': 'איוב',
        'Song of Songs': 'שיר השירים', 'Ruth': 'רות', 'Lamentations': 'איכה', 'Ecclesiastes': 'קהלת',
        'Esther': 'אסתר', 'Daniel': 'דניאל', 'Ezra': 'עזרא', 'Nehemiah': 'נחמיה', 'I Chronicles': 'דברי הימים א',
        'II Chronicles': 'דברי הימים ב'
    }
    for eng, heb in books.items():
        text = text.replace(eng, heb)
    return text

def get_jewish_calendar_info():
    cached_data = cache.get('jewish_cal_data')
    if cached_data:
        return cached_data
        
    cal_data = {'parasha': '', 'haftarah': '', 'holidays': []}
    
    try:
        url = 'https://www.hebcal.com/shabbat?cfg=json&geo=IL&M=on&lg=h'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=3)
        data = json.loads(response.read().decode('utf-8'))
        
        for item in data.get('items', []):
            cat = item.get('category')
            hebrew_text = item.get('hebrew', '')
            
            if cat == 'parashat':
                cal_data['parasha'] = hebrew_text
                leyning = item.get('leyning', {})
                if 'haftarah' in leyning:
                    cal_data['haftarah'] = translate_haftarah(leyning.get('haftarah', ''))
            elif cat in ['holiday', 'roshchodesh', 'fast']:
                if hebrew_text and hebrew_text not in cal_data['holidays']:
                    if not re.search('[a-zA-Z]', hebrew_text) and 'מבקרים' not in hebrew_text and 'שבת' not in hebrew_text:
                        cal_data['holidays'].append(hebrew_text)
                        
        cache.set('jewish_cal_data', cal_data, 60 * 60 * 6)
    except Exception:
        pass
        
    return cal_data

# ==========================================
# מנוע חיפוש חכם ומדורג
# ==========================================
def generate_word_variations(word):
    variations = set([word])
    if len(word) > 3 and word[0] in 'הבוכשמל':
        variations.add(word[1:])
    if len(word) > 4 and word[:2] in ['וה', 'בה', 'מה', 'שה', 'כה', 'וש', 'ול', 'וכ', 'ומ']:
        variations.add(word[2:])
    return list(variations)

def smart_hebrew_search(queryset, query, search_fields):
    if not query: return queryset
    words = [w for w in query.strip().split() if len(w) > 1]
    if not words:
        fallback_q = Q()
        for field in search_fields: fallback_q |= Q(**{f"{field}__icontains": query})
        return queryset.filter(fallback_q)

    main_q_and = Q()
    main_q_or = Q()
    
    for word in words:
        word_variations = generate_word_variations(word)
        word_q = Q()
        for var in word_variations:
            for field in search_fields: word_q |= Q(**{f"{field}__icontains": var})
        main_q_and &= word_q  
        main_q_or |= word_q   

    results = queryset.filter(main_q_and)
    if not results.exists(): results = queryset.filter(main_q_or)

    score_expr = Value(0)
    score_expr += Case(When(**{f"{search_fields[0]}__icontains": query}, then=Value(50)), default=Value(0), output_field=IntegerField())
    for word in words:
        variations = generate_word_variations(word)
        for var in variations:
            score_expr += Case(When(**{f"{search_fields[0]}__icontains": var}, then=Value(10)), default=Value(0), output_field=IntegerField())
            if len(search_fields) > 1:
                score_expr += Case(When(**{f"{search_fields[1]}__icontains": var}, then=Value(2)), default=Value(0), output_field=IntegerField())

    return results.annotate(relevance=score_expr).order_by('-relevance').distinct()

def get_smart_content(text, max_chars=16000):
    if not text: return ""
    if len(text) <= max_chars: return text
    keep_start = int(max_chars * 0.3) 
    keep_end = int(max_chars * 0.7)   
    return text[:keep_start] + "\n\n... [דיוני ביניים הוסרו לטובת קיצור] ...\n\n" + text[-keep_end:]

@csrf_exempt
def ai_chat_endpoint(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_question = data.get('question', '')
            mode = data.get('mode', 'content') 
            
            if not user_question: return JsonResponse({'answer': 'אנא כתוב שאלה.'})
            models_to_try = ['gemma-4-26b-a4b-it', 'gemini-1.5-flash', 'gemini-2.0-flash']

            if mode == 'nav':
                prompt = f"""אתה עוזר וירטואלי חייכן ומסביר פנים שתפקידו לעזור לגולשים לנווט ולהתמצא באתר. הגולש שואל אותך: '{user_question}' - חובה להפנות לעמוד הנכון ולשלב קישור."""
                final_response = None
                for m in models_to_try:
                    try:
                        response = client.models.generate_content(model=m, contents=prompt)
                        final_response = response.text
                        break 
                    except Exception as e: continue
                if final_response: return JsonResponse({'answer': final_response.replace('*', '')})
                else: return JsonResponse({'answer': 'עומס כבד בשרתי ה-AI. אנא נסה שוב.'})

            else:
                clean_question = re.sub(r'[^\w\s]', '', user_question)
                words = clean_question.split()
                valid_words = [w for w in words if len(w) > 1 and w not in ['מהי', 'מהו', 'האם', 'כיצד', 'איך', 'את', 'על', 'לי', 'תסביר', 'מתי', 'למה', 'מדוע', 'של', 'לו', 'אני', 'רוצה', 'לדעת', 'מה', 'מי', 'הוא', 'היא', 'הם', 'הן', 'יש', 'אין']]
                
                relevant_articles = []
                relevant_sections = []

                try:
                    exact_q = Q(title__icontains=clean_question) | Q(content__icontains=clean_question)
                    relevant_articles = list(Article.objects.filter(exact_q).filter(is_published=True).distinct()[:1])
                    relevant_sections = list(Section.objects.filter(exact_q).select_related('chapter', 'chapter__book').distinct()[:2])

                    if not relevant_articles and not relevant_sections and valid_words:
                        or_q = Q()
                        for word in valid_words: or_q |= Q(title__icontains=word) | Q(content__icontains=word)
                        if not or_q: or_q = Q(title__icontains=clean_question) | Q(content__icontains=clean_question)

                        potential_articles = list(Article.objects.filter(or_q).filter(is_published=True).distinct()[:20])
                        potential_sections = list(Section.objects.filter(or_q).select_related('chapter', 'chapter__book').distinct()[:30])
                        
                        def score_item(item):
                            t_val = str(getattr(item, 'title', ''))
                            c_val = str(getattr(item, 'content', getattr(item, 'text', '')))
                            text = (t_val + " " + c_val).lower()
                            score = sum(1 for w in valid_words if w in text)
                            for i in range(len(valid_words)-1):
                                if valid_words[i] + " " + valid_words[i+1] in text: score += 10
                            return score
                            
                        relevant_articles = sorted(potential_articles, key=score_item, reverse=True)[:1]
                        relevant_sections = sorted(potential_sections, key=score_item, reverse=True)[:2]
                except:
                    pass

                if not relevant_articles and not relevant_sections:
                    return JsonResponse({'answer': 'מצטער, לא מצאתי מידע בנושא זה. נסה לנסח אחרת.'})
                    
                context_text = ""
                MAX_CHARS = 15000 
                for article in relevant_articles: context_text += f"מקור: {article.title}\n{get_smart_content(str(article.content or ''), MAX_CHARS)}\n\n"
                for section in relevant_sections: context_text += f"מקור: סעיף {getattr(section, 'title', section.id)}\n{get_smart_content(str(getattr(section, 'content', getattr(section, 'text', ''))), MAX_CHARS)}\n\n"
                    
                prompt = f"אתה סייע תורני חכם באתר 'ספריית לייבוביץ'. ענה על השאלה: '{user_question}' מתוך המקורות המצורפים.\nמקורות:\n{context_text}"
                final_response = None
                for m in models_to_try:
                    try:
                        response = client.models.generate_content(model=m, contents=prompt)
                        final_response = response.text
                        break 
                    except Exception: continue
                
                if final_response: return JsonResponse({'answer': final_response.replace('*', '')})
                else: return JsonResponse({'answer': 'עומס כבד בשרתי ה-AI. אנא נסה שוב בעוד מספר שניות.'})
                
        except Exception:
            return JsonResponse({'answer': 'שגיאת שרת פנימית. אנא רענן את העמוד.'})
    return JsonResponse({'error': 'Invalid method'}, status=400)


def article_list(request):
    query = request.GET.get('q')
    
    if query:
        query = query.strip()
        published_articles = Article.objects.filter(is_published=True).order_by('-created_at')
        articles = smart_hebrew_search(published_articles, query, ['title', 'content'])
        return render(request, 'articles/article_list.html', {
            'articles': articles, 'latest_articles': None, 'reading_books': None, 'sale_books': None,
            'parasha_article': None, 'jewish_cal': None, 'query': query, 'current_page': 'home'
        })
        
    # ===============================================
    # מנגנון "ערבוב חכם יומי" (Smart Daily Shuffle)
    # ===============================================
    today_str = str(datetime.date.today())
    cache_key = f'home_dynamic_content_{today_str}'
    
    dynamic_content = cache.get(cache_key)
    
    if not dynamic_content:
        # 1. מאמר פרשה אקראי (רק אלו ששויכו לפרשה אמיתית)
        parasha_article = Article.objects.filter(is_published=True).exclude(
            Q(parasha__isnull=True) | 
            Q(parasha__exact='') | 
            Q(parasha__exact=',') | 
            Q(parasha__exact=',,') | 
            Q(parasha__icontains='general')
        ).order_by('?').first()
        
        # 2. מאמרים אחרונים אקראיים מתוך ה-15 האחרונים (שומר על עדכניות אך מגוון)
        recent_15 = list(Article.objects.filter(is_published=True).order_by('-created_at')[:15])
        if parasha_article and parasha_article in recent_15:
            recent_15.remove(parasha_article)
        latest_articles = random.sample(recent_15, min(2, len(recent_15)))
        
        # 3. 3 ספרים לקריאה אקראיים
        reading_books = list(Book.objects.filter(is_for_sale=False).order_by('?')[:3])
        
        # 4. 3 ספרים למכירה אקראיים
        sale_books = list(Book.objects.filter(is_for_sale=True).order_by('?')[:3])
        
        dynamic_content = {
            'parasha_article': parasha_article,
            'latest_articles': latest_articles,
            'reading_books': reading_books,
            'sale_books': sale_books
        }
        # שמירה במטמון - כל יום ייווצר עמוד בית חדש
        cache.set(cache_key, dynamic_content, 60 * 60 * 24)
        
    # חילוץ התוכן שנשמר
    parasha_article = dynamic_content['parasha_article']
    latest_articles = dynamic_content['latest_articles']
    reading_books = dynamic_content['reading_books']
    sale_books = dynamic_content['sale_books']

    # 5. הגרלת שאלה אקראית לשו"ת (מתוך 7 השאלות האחרונות)
    latest_qa = None
    try:
        from .models import QA
        qa_pool = list(QA.objects.order_by('-created_at')[:7])
        if qa_pool:
            latest_qa = random.choice(qa_pool)
    except Exception:
        pass
        
    # שליפת המידע מהלוח העברי (פרשה, הפטרה, צומות ומועדים של השבוע הנוכחי)
    jewish_cal = get_jewish_calendar_info()
    
    return render(request, 'articles/article_list.html', {
        'articles': None,
        'parasha_article': parasha_article,
        'latest_articles': latest_articles,
        'reading_books': reading_books,
        'sale_books': sale_books,
        'latest_qa': latest_qa,
        'jewish_cal': jewish_cal,
        'current_page': 'home'
    })


def article_detail(request, pk):
    article = get_object_or_404(Article, pk=pk, is_published=True)
    return render(request, 'articles/article_detail.html', {'article': article, 'current_page': 'articles'})

@login_required
def article_create(request):
    if request.method == 'POST':
        form = ArticleForm(request.POST)
        if form.is_valid(): form.save()
        return redirect('articles:list')
    return render(request, 'articles/article_form.html', {'form': ArticleForm(), 'current_page': 'articles'})

@login_required
def article_edit(request, pk):
    article = get_object_or_404(Article, pk=pk)
    if request.method == 'POST':
        form = ArticleForm(request.POST, instance=article)
        if form.is_valid(): form.save()
        return redirect('articles:detail', pk=article.pk)
    return render(request, 'articles/article_form.html', {'form': ArticleForm(instance=article), 'current_page': 'articles'})

@login_required
def article_delete(request, pk):
    article = get_object_or_404(Article, pk=pk)
    if request.method == 'POST': article.delete()
    return redirect('articles:list')

def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        phone = request.POST.get('phone', 'לא צוין')
        email = request.POST.get('email')
        subject = request.POST.get('subject', 'פנייה כללית')
        message = request.POST.get('message', '').strip()
        if not message: message = "[הגולש לא כתב תוכן]"

        recaptcha_response = request.POST.get('g-recaptcha-response')
        secret_key = '6LfC_VQtAAAAALw4ZpGG41Lvum-8VuMEMlTztvxQ' 
        data = urllib.parse.urlencode({'secret': secret_key, 'response': recaptcha_response}).encode('utf-8')
        req = urllib.request.Request('https://www.google.com/recaptcha/api/siteverify', data=data)
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))
        
        if not result.get('success'):
            messages.error(request, 'שגיאת אימות: המערכת זיהתה פעילות חשודה. נסה שוב.')
            return redirect('articles:contact')

        full_message = f"התקבלה פנייה חדשה מאתר הספרייה:\n\nשם: {name}\nטלפון: {phone}\nאימייל: {email}\nנושא הפנייה: {subject}\n\nהודעה:\n{message}"

        try:
            send_mail(
                subject=f"פנייה מהאתר: {subject}",
                message=full_message,
                from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'webmaster@localhost',
                recipient_list=['moshe111moshe111@gmail.com'],
                fail_silently=False,
            )
            messages.success(request, 'תודה! הודעתך נשלחה בהצלחה.')
        except Exception:
            messages.success(request, 'הפנייה התקבלה במערכת (מצב פיתוח).')
        return redirect('articles:contact')

    return render(request, 'articles/contact.html', {'current_page': 'contact'})

def calculator(request): 
    mida_book = Book.objects.filter(title__icontains='מידה').first()
    return render(request, 'articles/calculator.html', {'current_page': 'calculator', 'mida_book': mida_book})

def volume_calculator(request): 
    mida_book = Book.objects.filter(title__icontains='מידה').first()
    return render(request, 'articles/volume_calculator.html', {'current_page': 'calculator', 'mida_book': mida_book})

def weight_calculator(request): 
    mida_book = Book.objects.filter(title__icontains='מידה').first()
    return render(request, 'articles/weight_calculator.html', {'current_page': 'calculator', 'mida_book': mida_book})

@cache_page(60 * 60 * 24)
def about(request): 
    return render(request, 'articles/about.html', {'current_page': 'about'})

@cache_page(60 * 60 * 24)
def terms(request): 
    return render(request, 'articles/terms.html', {'current_page': 'terms'})

def books_list(request): 
    return render(request, 'articles/books_list.html', {'current_page': 'books'})

def qa_list(request): 
    try:
        from .models import QA
        questions = QA.objects.all().order_by('-created_at')
    except Exception:
        questions = None
    return render(request, 'articles/qa_list.html', {'questions': questions, 'current_page': 'qa'})

def article_index(request): 
    published_articles = Article.objects.filter(is_published=True).order_by('title')
    grouped_articles = {}
    for article in published_articles:
        if article.title:
            first_letter = article.title.strip()[0]
            if first_letter not in grouped_articles: grouped_articles[first_letter] = []
            grouped_articles[first_letter].append(article)
    sorted_groups = {k: grouped_articles[k] for k in sorted(grouped_articles.keys())}
    return render(request, 'articles/article_index.html', {'grouped_articles': sorted_groups, 'current_page': 'articles'})

def recently_added(request): 
    recent_articles = Article.objects.filter(is_published=True).order_by('-id')[:12]
    return render(request, 'articles/recently_added.html', {'articles': recent_articles, 'current_page': 'recently_added'})

def parasha_list(request): 
    selected_parasha = request.GET.get('p')
    articles = None
    if selected_parasha:
        parasha_q = Q(parasha__icontains=f",{selected_parasha},") | Q(parasha=selected_parasha)
        articles = Article.objects.filter(parasha_q, is_published=True).order_by('-created_at')
    return render(request, 'articles/parasha_list.html', {'current_page': 'parasha', 'selected_parasha': selected_parasha, 'articles': articles})

def book_detail(request, pk): 
    return render(request, 'articles/book_detail.html', {'book': get_object_or_404(Book, pk=pk), 'current_page': 'books'})

def books(request): 
    books_ordered = Book.objects.all().order_by('order', 'title')
    return render(request, 'articles/books_list.html', {'books': books_ordered, 'current_page': 'books'})

def live_search(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2: return JsonResponse({'results': []})
    cache_key = f'live_search_{q}'
    cached_results = cache.get(cache_key)
    if cached_results: return JsonResponse({'results': cached_results})
    
    books_qs = Book.objects.all()
    articles_qs = Article.objects.filter(is_published=True)
    books = smart_hebrew_search(books_qs, q, ['title', 'author']).only('id', 'title')[:3]
    articles = smart_hebrew_search(articles_qs, q, ['title', 'content']).only('id', 'title')[:4]
    
    results = []
    for book in books: results.append({'title': book.title, 'type': 'ספר שלם', 'icon': 'bi-journal-bookmark-fill', 'url': reverse('articles:book_detail', args=[book.id])})
    for article in articles: results.append({'title': article.title, 'type': 'מאמר', 'icon': 'bi-file-earmark-text', 'url': reverse('articles:detail', args=[article.id])})
        
    cache.set(cache_key, results, timeout=300)
    return JsonResponse({'results': results})

def _get_or_create_cart(request):
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(user=request.user)
        return cart
    else:
        if not request.session.session_key: request.session.create()
        cart, created = Cart.objects.get_or_create(session_id=request.session.session_key)
        return cart

def add_to_cart(request, book_id):
    book = get_object_or_404(Book, id=book_id, is_for_sale=True)
    cart = _get_or_create_cart(request)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, book=book)
    if not created:
        cart_item.quantity += 1
        cart_item.save()
    messages.success(request, f'הספר "{book.title}" נוסף לעגלת הקניות בהצלחה.')
    return redirect('articles:cart_detail')

def remove_from_cart(request, item_id):
    cart = _get_or_create_cart(request)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    item.delete()
    messages.info(request, 'הפריט הוסר מעגלת הקניות.')
    return redirect('articles:cart_detail')

def cart_detail(request):
    cart = _get_or_create_cart(request)
    items = cart.items.select_related('book').all()
    total_price = sum(item.get_total_price() for item in items)
    return render(request, 'articles/cart_detail.html', {'cart': cart, 'items': items, 'total_price': total_price, 'current_page': 'cart'})

def checkout(request):
    cart = _get_or_create_cart(request)
    items = cart.items.select_related('book').all()
    if not items:
        messages.error(request, 'העגלה שלך ריקה. אנא הוסף ספרים לפני המעבר לקופה.')
        return redirect('articles:books')
    total_price = sum(item.get_total_price() for item in items)
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        city = request.POST.get('city')
        zip_code = request.POST.get('zip_code', '')
        notes = request.POST.get('notes', '')

        order = Order.objects.create(
            first_name=first_name, last_name=last_name, email=email, phone=phone,
            address=address, city=city, zip_code=zip_code, notes=notes,
            total_paid=total_price, status='pending'
        )
        for item in items:
            OrderItem.objects.create(order=order, book=item.book, price=item.book.price, quantity=item.quantity)
        cart.items.all().delete()
        try: send_order_confirmation(order)
        except Exception: pass
        return render(request, 'articles/order_success.html', {'order': order})
    return render(request, 'articles/checkout.html', {'items': items, 'total_price': total_price, 'current_page': 'cart'})

@receiver([post_save, post_delete], sender=Article)
@receiver([post_save, post_delete], sender=Book)
def clear_cache_on_db_change(sender, instance, **kwargs):
    cache.clear()