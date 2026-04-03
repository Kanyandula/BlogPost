import uuid
from django.db import models


class Subscriber(models.Model):
	email = models.EmailField(unique=True)
	token = models.UUIDField(default=uuid.uuid4, editable=False)
	confirmed = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.email
