from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from .models import UserProfile, Detection


class UserRegistrationForm(forms.Form):
    ROLE_CHOICES = [
        ('farmer', '🌾 Farmer — I want to scan my cattle for FMD'),
        ('vet',    '🩺 Veterinary Doctor — I provide veterinary services'),
    ]

    first_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'First Name', 'class': 'form-control'}),
    )
    last_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'Last Name', 'class': 'form-control'}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'Email Address', 'class': 'form-control'}),
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'role-radio'}),
        initial='farmer',
    )
    # Vet-only optional fields
    license_number = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Veterinary License Number (optional)',
            'class': 'form-control',
        }),
    )
    specialization = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Specialization e.g. Bovine Medicine (optional)',
            'class': 'form-control',
        }),
    )
    phone_number = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Phone Number e.g. +256700123456 (optional)',
            'class': 'form-control',
        }),
    )
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={'placeholder': 'Password (min 8 chars)', 'class': 'form-control'}),
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password', 'class': 'form-control'}),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        pwd  = cleaned.get('password')
        cpwd = cleaned.get('confirm_password')
        if pwd and cpwd and pwd != cpwd:
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned

    def save(self):
        data  = self.cleaned_data
        role  = data['role']
        email = data['email'].lower()

        user = User.objects.create_user(
            username=email,
            email=email,
            password=data['password'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            # Vets cannot log in until approved — keep account inactive
            is_active=(role != 'vet'),
        )

        profile = user.profile
        profile.role = role

        # Always store phone if provided (useful for admins too)
        if data.get('phone_number'):
            profile.phone_number = data['phone_number']

        if role == 'vet':
            profile.is_approved = False
            if data.get('license_number'):
                profile.license_number = data['license_number']
            if data.get('specialization'):
                profile.specialization = data['specialization']
        else:
            profile.is_approved = True

        profile.save()
        return user


class VetRegistrationForm(forms.Form):
    """Admin form to register a veterinary doctor (pre-approved, immediately active)."""
    full_name = forms.CharField(
        max_length=100, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'})
    )
    phone_number = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number e.g. +256700123456'})
    )
    license_number = forms.CharField(
        max_length=50, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'License Number'})
    )
    specialization = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Specialization (e.g. Bovine Medicine)'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Set Password'}),
        min_length=8,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('confirm_password'):
            raise forms.ValidationError('Passwords do not match.')
        return cleaned

    def save(self):
        full_name = self.cleaned_data['full_name'].strip()
        parts = full_name.split(' ', 1)
        first_name = parts[0]
        last_name  = parts[1] if len(parts) > 1 else ''
        email = self.cleaned_data['email']

        base_username = email.split('@')[0]
        username = base_username
        counter  = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            password=self.cleaned_data['password'],
            first_name=first_name,
            last_name=last_name,
            is_active=True,   # Admin-created vets are immediately active
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role         = 'vet'
        profile.phone_number = self.cleaned_data.get('phone_number', '')
        profile.license_number  = self.cleaned_data.get('license_number', '')
        profile.specialization  = self.cleaned_data.get('specialization', '')
        profile.is_verified  = True
        profile.is_approved  = True   # Admin-created vets are pre-approved
        profile.save()
        return user


class ProfileUpdateForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
    )
    last_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
    )

    class Meta:
        model = UserProfile
        fields = ['phone_number', 'farm_name', 'location', 'license_number', 'specialization', 'profile_image']
        widgets = {
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'farm_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Farm name'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Location'}),
            'license_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'License number'}),
            'specialization': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Specialization'}),
            'profile_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png,image/jpg,image/webp'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email
        if self.instance and self.instance.role != 'vet':
            self.fields.pop('license_number', None)
            self.fields.pop('specialization', None)

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        qs = User.objects.filter(email=email)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError('This email is already used by another account.')
        return email

    def clean_profile_image(self):
        image = self.cleaned_data.get('profile_image')
        if image:
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError('Profile image size cannot exceed 5MB.')
            valid_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
            if hasattr(image, 'content_type') and image.content_type not in valid_types:
                raise forms.ValidationError('Only JPG, PNG, and WEBP images are allowed.')
        return image

    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.user:
            self.user.first_name = self.cleaned_data.get('first_name', '')
            self.user.last_name = self.cleaned_data.get('last_name', '')
            self.user.email = self.cleaned_data.get('email', '').lower()
            self.user.username = self.user.email
            if commit:
                self.user.save()
        if commit:
            profile.save()
        return profile


class UserLoginForm(AuthenticationForm):
    """Login using email and password"""
    username = forms.CharField(
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        })
    )


class DetectionUploadForm(forms.ModelForm):
    """Form for uploading cattle images"""

    class Meta:
        model = Detection
        fields = ['image', 'animal_id', 'location', 'notes']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/jpeg,image/png,image/jpg,image/webp',
            }),
            'animal_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Animal ID (optional)',
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Location (optional)',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes (optional)',
            }),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Image file size cannot exceed 10MB.')
            valid_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
            if hasattr(image, 'content_type') and image.content_type not in valid_types:
                raise forms.ValidationError('Only JPG, PNG, and WEBP images are allowed.')
        return image