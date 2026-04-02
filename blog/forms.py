from django import forms

from blog.models import BlogPost, Comment


class CommentForm(forms.ModelForm):

	class Meta:
		model = Comment
		fields = ['body']
		widgets = {
			'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write a comment...'}),
		}


class CreateBlogPostForm(forms.ModelForm):

	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image', 'category', 'tags', 'status']
		widgets = {
			'tags': forms.CheckboxSelectMultiple(),
		}


class UpdateBlogPostForm(forms.ModelForm):

	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image', 'category', 'tags', 'status']
		widgets = {
			'tags': forms.CheckboxSelectMultiple(),
		}

	def save(self, commit=True):
		blog_post = self.instance
		blog_post.title = self.cleaned_data['title']
		blog_post.body = self.cleaned_data['body']
		blog_post.category = self.cleaned_data['category']
		blog_post.status = self.cleaned_data['status']

		if self.cleaned_data['image']:
			blog_post.image = self.cleaned_data['image']

		if commit:
			blog_post.save()
			self.save_m2m()
		return blog_post
