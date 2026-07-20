import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from articles.models import Book, Chapter, Section

# 1. מוצאים את הספר
book = Book.objects.filter(title__icontains="נספח ב").first()
if book:
    # 2. מוצאים את הפרק העליון שנוצר בטעות
    chapter = Chapter.objects.filter(book=book, title__icontains="תוכן הנספח").first()
    if chapter:
        # משנים את שם הפרק הראשי ל"מבוא"
        chapter.title = "מבוא"
        chapter.save()
        print("✅ פרק 'תוכן הנספח' שונה ל-'מבוא'")
        
        # 3. מוצאים ומוחקים את הסעיף המיותר של "גדר תקנת..."
        bad_section = Section.objects.filter(chapter=chapter, title__icontains="גדר תקנת").first()
        if bad_section:
            bad_section.delete()
            print("✅ הסעיף המיותר נמחק בהצלחה")
            
        # 4. משנים את שם סעיף המבוא הפנימי ל"פתיחה" כדי שלא יהיה כתוב "מבוא" פעמיים
        mavo_section = Section.objects.filter(chapter=chapter, title__icontains="מבוא").first()
        if mavo_section:
            mavo_section.title = "פתיחה"
            mavo_section.save()
            print("✅ סעיף ה'מבוא' שונה ל-'פתיחה' למניעת כפילות בתפריט")
            
        print("🚀 התיקון בוצע בהצלחה! רענן את האתר.")
    else:
        print("❌ לא מצאתי פרק בשם 'תוכן הנספח'. (אולי הוא כבר שונה?)")
else:
    print("❌ לא מצאתי ספר שמתחיל במילים 'נספח ב'.")