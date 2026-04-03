import cv2
import os

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