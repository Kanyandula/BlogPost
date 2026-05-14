from django import forms


class TiptapWidget(forms.Textarea):
	"""Renders a hidden <textarea> + a Tiptap mount.

	The JS bundle (static/blog/tiptap.js) initialises Tiptap on every
	.tiptap-shell and mirrors editor.getHTML() back to the hidden textarea
	on every input event. Server receives plain text (the HTML string),
	exactly as it did with CKEditor 5.
	"""

	template_name = 'blog/widgets/tiptap.html'

	class Media:
		css = {'all': ['blog/tiptap.css']}
		js = ['blog/tiptap.js']

	def __init__(self, attrs=None):
		defaults = {'hidden': True, 'data-tiptap-input': ''}
		super().__init__({**defaults, **(attrs or {})})
