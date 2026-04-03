from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import BlogPost, Category


class BlogPostSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return BlogPost.objects.filter(status='published').order_by('-date_updated')

    def lastmod(self, obj):
        return obj.date_updated

    def location(self, obj):
        return reverse('blog:detail', args=[obj.slug])


class CategorySitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.6

    def items(self):
        return Category.objects.all()

    def location(self, obj):
        return f'/?category={obj.slug}'


class StaticSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.5

    def items(self):
        return ['home', 'about', 'contact', 'api']

    def location(self, item):
        return reverse(item)
