from rest_framework import serializers

from account.models import Account, UserProfile


# class LoginSerializer(serializers.ModelSerializer):
# 	class Meta:
# 		model = Account
# 		fields = ['email', 'password',]

# 		extra_kwargs = {'password': {'write_only': True}}

# 	def validate(self, data):
# 		password = data.get('password')
# 		email = data.get('email')


class RegistrationSerializer(serializers.ModelSerializer):

	password2 				= serializers.CharField(style={'input_type': 'password'}, write_only=True)

	class Meta:
		model = Account
		fields = ['email', 'username', 'password', 'password2']
		extra_kwargs = {
				'password': {'write_only': True},
		}	


	def	save(self):

		account = Account(
					email=self.validated_data['email'],
					username=self.validated_data['username']
				)
		password = self.validated_data['password']
		password2 = self.validated_data['password2']
		if password != password2:
			raise serializers.ValidationError({'password': 'Passwords must match.'})
		account.set_password(password)
		account.save()
		return account

class AccountPropertiesSerializer(serializers.ModelSerializer):

	class Meta:
		model = Account
		fields = ['pk', 'email', 'username', ]

class ChangePasswordSerializer(serializers.Serializer):

	old_password 				= serializers.CharField(required=True)
	new_password 				= serializers.CharField(required=True)
	confirm_new_password 		= serializers.CharField(required=True)


class UserProfileSerializer(serializers.ModelSerializer):
	username = serializers.CharField(source='user.username', read_only=True)
	email = serializers.CharField(source='user.email', read_only=True)
	date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)

	class Meta:
		model = UserProfile
		fields = ['username', 'email', 'date_joined', 'bio', 'avatar', 'location',
				  'website', 'twitter', 'facebook', 'instagram', 'linkedin']
		read_only_fields = ['username', 'email', 'date_joined']
