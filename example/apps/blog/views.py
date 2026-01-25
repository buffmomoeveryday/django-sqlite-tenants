from django.http import HttpRequest
from django.shortcuts import render, redirect
from .models import Blog
from django.views import View

from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required


class BlogListView(View):
    def get(self, request: HttpRequest):
        return render(
            request,
            "blog/list_blog.html",
            context={"blogs": Blog.objects.all()},
        )


class BlogCreateView(View):
    # @method_decorator(login_required)
    def get(self, request: HttpRequest):
        return render(request, "blog/create_blog.html", context={})

    # @method_decorator(login_required)
    def post(self, request: HttpRequest):
        name = request.POST.get("name")
        post = request.POST.get("post")
        Blog.objects.create(name=name, post=post)
        return redirect("blog_create")


class BlogDetail(View):
    def get(self, request: HttpRequest, pk: int):
        blog = Blog.objects.get(pk=pk)
        return render(request, "blog/detail_blog.html", context={"blog": blog})


class BlogEditView(View):
    @method_decorator(login_required)
    def get(self, request: HttpRequest, pk: int):
        blog = Blog.objects.get(pk=pk)
        return render(request, "blog/edit_blog.html", context={"blog": blog})

    @method_decorator(login_required)
    def post(self, request: HttpRequest, pk: int):
        blog = Blog.objects.get(pk=pk)
        blog.name = request.POST.get("name")
        blog.post = request.POST.get("post")
        blog.save()
        return redirect("blog_detail", pk=blog.pk)
