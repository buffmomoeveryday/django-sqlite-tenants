from django.contrib.auth.models import User
from django.db import models


# Create your models here.
class Blog(models.Model):
    name = models.CharField(verbose_name="Blog")
    post = models.CharField(verbose_name="Post", null=True, blank=True)
