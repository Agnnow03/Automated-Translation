import os
from flask import Flask, render_template, request
from translation_engine import TranslationService, SentenceCorrector
from constants.language_names import ENGLISH, POLISH, AVAILABLE_LANGUAGES

app = Flask(__name__)

translation_service = TranslationService()
corrector = SentenceCorrector(translation_service.memory)

@app.route('/', methods=['GET', 'POST'])
def index():
    source_lang = request.form.get('source_lang', POLISH)
    target_lang = request.form.get('target_lang', ENGLISH)
    text = request.form.get('text', '')
    target_only = request.form.get('target_only') == '1'
    translations = []
    corrections = []
    error = None

    if request.method == 'POST':
        try:
            translations = translation_service.translate_text(text, source_lang, target_lang)
            if not target_only:
                corrections = corrector.propose_corrections(text, source_lang)
            # Also propose corrections for each translated proposal (in target language)
            for prop in translations:
                trans_text = prop.get('translation')
                if trans_text:
                    trans_sugg = corrector.propose_corrections(trans_text, target_lang)
                    # mark suggestion reasons as translation-specific
                    for s in trans_sugg:
                        s['reason'] = 'Translation suggestion: ' + s.get('reason', '')
                        corrections.append(s)
        except Exception as exc:
            error = str(exc)

    return render_template(
        'index.html',
        source_lang=source_lang,
        target_lang=target_lang,
        languages=AVAILABLE_LANGUAGES,
        text=text,
        target_only=target_only,
        translations=translations,
        corrections=corrections,
        error=error,
        ENGLISH=ENGLISH,
        POLISH=POLISH,
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
