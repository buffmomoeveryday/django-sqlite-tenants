from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import BlogForm
from .models import Blog


class BlogListView(View):
    def get(self, request: HttpRequest):
        return render(
            request,
            "blog/list_blog.html",
            context={"blogs": Blog.objects.all()},
        )


class BlogCreateView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest):
        return render(request, "blog/create_blog.html", {"form": BlogForm()})

    def post(self, request: HttpRequest):
        form = BlogForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("blog_list_view")
        return render(request, "blog/create_blog.html", {"form": form}, status=400)


class BlogDetail(View):
    def get(self, request: HttpRequest, pk: int):
        blog = get_object_or_404(Blog, pk=pk)
        return render(request, "blog/detail_blog.html", {"blog": blog})


class BlogEditView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, pk: int):
        blog = get_object_or_404(Blog, pk=pk)
        return render(
            request,
            "blog/edit_blog.html",
            {"blog": blog, "form": BlogForm(instance=blog)},
        )

    def post(self, request: HttpRequest, pk: int):
        blog = get_object_or_404(Blog, pk=pk)
        form = BlogForm(request.POST, instance=blog)
        if form.is_valid():
            blog = form.save()
            return redirect("blog_detail", pk=blog.pk)
        return render(
            request,
            "blog/edit_blog.html",
            {"blog": blog, "form": form},
            status=400,
        )
