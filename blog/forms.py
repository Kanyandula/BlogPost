from django import forms

from blog.models import BlogPost, Comment
from blog.widgets import TiptapWidget


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
			'body': TiptapWidget(),
		}


class UpdateBlogPostForm(forms.ModelForm):

	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image', 'category', 'tags', 'status']
		widgets = {
			'tags': forms.CheckboxSelectMultiple(),
			'body': TiptapWidget(),
		}

	def save(self, commit=True):
		if not self.cleaned_data.get('image'):
			self.cleaned_data['image'] = self.instance.image
		return super().save(commit=commit)
