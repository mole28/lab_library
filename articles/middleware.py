from .models import VisitorLog

class VisitorTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/static/') and not request.path.startswith('/media/'):
            try:
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip = x_forwarded_for.split(',')[0]
                else:
                    ip = request.META.get('REMOTE_ADDR')
                
                # בדיקה בטוחה האם שדה המשתמש קיים ומאומת
                user = None
                if hasattr(request, 'user') and request.user.is_authenticated:
                    user = request.user

                VisitorLog.objects.create(
                    ip_address=ip,
                    path=request.path,
                    user=user,
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            except Exception:
                # מונע מכל בעיית רישום פוטנציאלית להפיל את האתר
                pass
        
        response = self.get_response(request)
        return response