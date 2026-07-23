from django.contrib import admin
from .models import Article, Book, Chapter, Section, Cart, CartItem, Order, OrderItem, QA, VisitorLog

# ==========================================
# ניהול מאמרים
# ==========================================
@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'parasha', 'is_published', 'created_at')
    list_filter = ('is_published', 'created_at')
    search_fields = ('title', 'content', 'parasha')

# ==========================================
# ניהול ספרים
# ==========================================
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    # העמודה order נוספה לכאן לתצוגה
    list_display = ('title', 'author', 'order', 'price', 'stock', 'is_for_sale')
    
    # העמודה order נוספה לכאן כדי שתוכל לערוך אותה ישירות מהרשימה בלי להיכנס לספר!
    list_editable = ('order', 'price', 'stock', 'is_for_sale')
    
    list_filter = ('is_for_sale',)
    search_fields = ('title', 'author')

@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('title', 'book', 'order')
    list_filter = ('book',)
    search_fields = ('title',)
    list_editable = ('order',)

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'chapter', 'order')
    list_filter = ('chapter__book',)
    search_fields = ('title', 'content')
    list_editable = ('order',)

# ==========================================
# ניהול חנות והזמנות
# ==========================================
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('price',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'status', 'total_paid', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('first_name', 'last_name', 'email', 'phone', 'id')
    list_editable = ('status',)
    inlines = [OrderItemInline]

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at')

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'book', 'quantity')

@admin.register(QA)
class QAAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'created_at')
    search_fields = ('question', 'answer', 'category')
    list_filter = ('category', 'created_at')

# ==========================================
# ניהול ומעקב מבקרים (לצורכי סקרים ובדיקות)
# ==========================================
@admin.register(VisitorLog)
class VisitorLogAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'path', 'user', 'timestamp')
    list_filter = ('timestamp', 'user')
    search_fields = ('ip_address', 'path', 'user__username', 'user_agent')
    readonly_fields = ('ip_address', 'path', 'user', 'user_agent', 'timestamp')
    
    # מונע מחיקה או עריכה בטעות של הלוגים דרך האדמין (אופציונלי - שומר על אמינות המעקב)
    def has_add_permission(self, request):
        return False