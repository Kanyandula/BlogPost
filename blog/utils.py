import cv2
import os
from functools import wraps

from django.http import HttpResponse
from django.shortcuts import redirect
from django_htmx.http import trigger_client_event

ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}


def is_image_aspect_ratio_valid(img_url):
	img = cv2.imread(img_url)
	if img is None:
		return False
	dimensions = tuple(img.shape[1::-1]) # gives: (width, height)
	aspect_ratio = dimensions[0] / dimensions[1] # divide w / h
	if aspect_ratio < 1:
		return False
	return True


def is_image_size_valid(img_url, mb_limit):
	image_size = os.path.getsize(img_url)
	if image_size > mb_limit:
		return False
	return True


def validate_image_upload(image):
	"""Validate image MIME type and size before writing to disk."""
	if hasattr(image, 'content_type') and image.content_type not in ALLOWED_IMAGE_TYPES:
		return False, "Unsupported image format. Allowed: JPEG, PNG, WebP, GIF."
	if hasattr(image, 'size') and image.size > 2 * 1024 * 1024:
		return False, "Image too large. Images must be less than 2 MB."
	return True, None


def trigger_toast(response, message, toast_type='success'):
	"""Attach an HX-Trigger header that fires the showToast custom event."""
	return trigger_client_event(response, 'showToast', {'message': message, 'type': toast_type})


def htmx_login_required(view_func):
	"""Decorator that returns a 401 + toast for unauthenticated HTMX requests
	instead of redirecting to the login page (which would swap login HTML
	into the button target)."""
	@wraps(view_func)
	def wrapper(request, *args, **kwargs):
		if not request.user.is_authenticated:
			if getattr(request, 'htmx', False):
				response = HttpResponse(status=401)
				response['HX-Reswap'] = 'none'
				trigger_toast(response, 'Please log in to continue', 'error')
				return response
			return redirect('must_authenticate')
		return view_func(request, *args, **kwargs)
	return wrapper