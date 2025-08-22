from django.contrib import admin
from django.urls import path

admin.site.site_header = "TG-Production Bot"
urlpatterns = [path("admin/", admin.site.urls)]