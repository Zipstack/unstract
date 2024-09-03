from django.contrib import admin

from .models import APIDeployment, APIKey

admin.site.register([APIDeployment, APIKey])
