from rest_framework import serializers

import cv2
import sys
import os
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.storage import FileSystemStorage
IMAGE_SIZE_MAX_BYTES = 1024 * 1024 * 2 # 2MB
MIN_TITLE_LENGTH = 5
MIN_BODY_LENGTH = 50

from blog.models import BlogPost, Category, Tag, Comment

from blog.utils import is_image_aspect_ratio_valid, is_image_size_valid, validate_image_upload


class CategorySerializer(serializers.ModelSerializer):
	class Meta:
		model = Category
		fields = ['pk', 'name', 'slug', 'description']


class TagSerializer(serializers.ModelSerializer):
	class Meta:
		model = Tag
		fields = ['pk', 'name', 'slug']


class CommentSerializer(serializers.ModelSerializer):
	username = serializers.CharField(source='author.username', read_only=True)
	replies = serializers.SerializerMethodField()

	class Meta:
		model = Comment
		fields = ['pk', 'post', 'username', 'parent', 'body', 'created_at', 'replies']
		read_only_fields = ['post', 'username', 'created_at']

	def get_replies(self, obj):
		if obj.replies.exists():
			return CommentSerializer(obj.replies.filter(is_active=True), many=True).data
		return []


class CommentCreateSerializer(serializers.ModelSerializer):
	class Meta:
		model = Comment
		fields = ['body', 'parent']

	def validate_parent(self, value):
		if value and value.parent is not None:
			raise serializers.ValidationError("Replies can only be one level deep.")
		return value


class BlogPostSerializer(serializers.ModelSerializer):

	username = serializers.SerializerMethodField('get_username_from_author')
	author_avatar = serializers.SerializerMethodField('get_author_avatar')
	image 	 = serializers.SerializerMethodField('validate_image_url')
	category = CategorySerializer(read_only=True)
	tags = TagSerializer(many=True, read_only=True)
	like_count = serializers.IntegerField(source='likes.count', read_only=True)
	comment_count = serializers.IntegerField(source='comments.count', read_only=True)
	reading_time = serializers.IntegerField(read_only=True)

	class Meta:
		model = BlogPost
		fields = ['pk', 'title', 'slug', 'body', 'image', 'date_updated', 'username',
				  'author_avatar', 'category', 'tags', 'status', 'is_featured', 'view_count',
				  'like_count', 'comment_count', 'reading_time']


	def get_username_from_author(self, blog_post):
		username = blog_post.author.username
		return username

	def get_author_avatar(self, blog_post):
		try:
			avatar = blog_post.author.profile.avatar
			if avatar:
				return avatar.url
		except blog_post.author.profile.RelatedObjectDoesNotExist:
			pass
		return None

	def validate_image_url(self, blog_post):
		image = blog_post.image
		if not image:
			return None
		new_url = image.url
		if "?" in new_url:
			new_url = image.url[:image.url.rfind("?")]
		return new_url


class BlogPostUpdateSerializer(serializers.ModelSerializer):

	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image']

	def validate(self, blog_post):
		try:
			title = blog_post['title']
			if len(title) < MIN_TITLE_LENGTH:
				raise serializers.ValidationError({"response": "Enter a title longer than " + str(MIN_TITLE_LENGTH) + " characters."})

			body = blog_post['body']
			if len(body) < MIN_BODY_LENGTH:
				raise serializers.ValidationError({"response": "Enter a body longer than " + str(MIN_BODY_LENGTH) + " characters."})
		except KeyError:
			pass

		try:
			image = blog_post['image']

			# Validate MIME type and size before writing to disk
			is_valid, error_msg = validate_image_upload(image)
			if not is_valid:
				raise serializers.ValidationError({"response": error_msg})

			url = os.path.join(settings.TEMP, str(image))
			storage = FileSystemStorage(location=url)
			try:
				with storage.open('', 'wb+') as destination:
					for chunk in image.chunks():
						destination.write(chunk)

				if not is_image_aspect_ratio_valid(url):
					raise serializers.ValidationError({"response": "Image height must not exceed image width. Try a different image."})
			finally:
				if os.path.exists(url):
					os.remove(url)
		except KeyError:
			pass
		return blog_post

		

class BlogPostCreateSerializer(serializers.ModelSerializer):


	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image', 'date_updated', 'author']


	def save(self):
		try:
			image = self.validated_data['image']
			title = self.validated_data['title']
			if len(title) < MIN_TITLE_LENGTH:
				raise serializers.ValidationError({"response": "Enter a title longer than " + str(MIN_TITLE_LENGTH) + " characters."})

			body = self.validated_data['body']
			if len(body) < MIN_BODY_LENGTH:
				raise serializers.ValidationError({"response": "Enter a body longer than " + str(MIN_BODY_LENGTH) + " characters."})

			# Validate MIME type and size before writing to disk
			is_valid, error_msg = validate_image_upload(image)
			if not is_valid:
				raise serializers.ValidationError({"response": error_msg})

			blog_post = BlogPost(
								author=self.validated_data['author'],
								title=title,
								body=body,
								image=image,
								)

			url = os.path.join(settings.TEMP, str(image))
			storage = FileSystemStorage(location=url)
			try:
				with storage.open('', 'wb+') as destination:
					for chunk in image.chunks():
						destination.write(chunk)

				if not is_image_aspect_ratio_valid(url):
					raise serializers.ValidationError({"response": "Image height must not exceed image width. Try a different image."})
			finally:
				if os.path.exists(url):
					os.remove(url)

			blog_post.save()
			return blog_post
		except KeyError:
			raise serializers.ValidationError({"response": "You must have a title, some content, and an image."})



