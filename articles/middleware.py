from .models import VisitorLog

class VisitorTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # מתעד רק בקשות רגילות ולא קבצים סטטיים או מדיה כדי לא ללכלך את מסד הנתונים
        if not request.path.startswith('/static/') and not request.path.startswith('/media/'):
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # שמירת הנתונים במסד הנתונים
            VisitorLog.objects.create(
                ip_address=ip,
                path=request.path,
                user=request.user if request.user.is_authenticated else None,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        
        response = self.get_response(request)
        return response