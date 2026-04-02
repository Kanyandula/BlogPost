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
		# Keep existing image if no new one uploaded
		if not self.cleaned_data.get('image'):
			self.cleaned_data['image'] = self.instance.image
		return super().save(commit=commit)
