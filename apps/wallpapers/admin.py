"""Django admin registration — internal-staff content curation (session auth, Constitution II).

This is the internal-staff tool, distinct from both API tiers. Model-level validation
(``Tag.clean`` → ``validate_tag_slug``) is enforced here via ``full_clean`` on save, so the
reserved slug ``all`` cannot be created through the admin either (analyze U2).
"""

from django.contrib import admin

from apps.wallpapers.models import Category, Collection, CollectionItem, Tag, Wallpaper


class CollectionItemInline(admin.TabularInline):
    model = CollectionItem
    extra = 1
    ordering = ["position"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "slug", "name"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["id", "slug", "name"]
    prepopulated_fields = {"slug": ["name"]}

    def save_model(self, request, obj, form, change):
        obj.full_clean()  # runs validate_tag_slug — reserved "all" is rejected
        super().save_model(request, obj, form, change)


@admin.register(Wallpaper)
class WallpaperAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "category", "orientation", "is_premium", "status", "created_at"]
    list_filter = ["status", "is_premium", "orientation", "category"]
    search_fields = ["title"]
    filter_horizontal = ["tags"]


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["id", "slug", "title", "is_premium", "created_at"]
    prepopulated_fields = {"slug": ["title"]}
    inlines = [CollectionItemInline]
