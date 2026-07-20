from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def send_order_confirmation(order):
    """נשלח אוטומטית ברגע שהלקוח מסיים את הקנייה בקופה"""
    subject = f"אישור הזמנה #{order.id} - ספריית לייבוביץ"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [order.email]

    # מעביר את אובייקט ההזמנה לתבנית העיצוב
    context = {'order': order}

    html_content = render_to_string('articles/emails/order_confirmation.html', context)
    text_content = f"תודה רבה על הזמנתך! מספר ההזמנה שלך הוא {order.id}."

    msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=True)

def send_shipping_update(order):
    """נשלח אוטומטית ברגע שאתה משנה סטטוס ל'נשלח' בפאנל הניהול"""
    subject = f"ההזמנה שלך יצאה לדרך! (הזמנה #{order.id})"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [order.email]

    context = {'order': order}
    html_content = render_to_string('articles/emails/order_shipped.html', context)
    text_content = f"ההזמנה שלך נשלחה! מספר מעקב: {order.tracking_number}"

    msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=True)