import email
from turtle import title
from unicodedata import name
from django import forms

from blog.models import BlogPost 


class CreateBlogPostForm(forms.ModelForm):

	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image']


class UpdateBlogPostForm(forms.ModelForm):

	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image']

	def save(self, commit=True):
		blog_post = self.instance
		blog_post.title = self.cleaned_data['title']
		blog_post.body = self.cleaned_data['body']

		if self.cleaned_data['image']:
			blog_post.image = self.cleaned_data['image']

		if commit:
			blog_post.save()
		return blog_post

class DeleteBlogPost(forms.ModelForm):
	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image']

def should_be_empty(value):
    if value:
        raise forms.ValidationError('Field is not empty')


class ContactForm(forms.Form):
    name = forms.CharField(max_length=80)
    title = forms.CharField(max_length=80)
    message = forms.CharField(widget=forms.Textarea)
    email = forms.EmailField()
    forcefield = forms.CharField(
        required=False, widget=forms.HiddenInput, label="Leave empty", validators=[should_be_empty])

	

