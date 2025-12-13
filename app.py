from flask import Flask, render_template, request, redirect, url_for
import json
import os
import re

app = Flask(__name__)

# root directory
@app.route('/')
def index():
    return render_template('index.html')
    
# watch news
@app.route('/news', methods=['POST'])
def news():
    level = request.form.get('cefr')
    count = int(request.form.get('count'))
    news_type = request.form.get('news_type')

    # suppose is txt file
    news_path = f"data/news/{news_type}.txt"

    with open(news_path, 'r', encoding='utf-8') as f:
        news_content = f.read()

    return render_template(
        'news.html',
        news=news_content,
        level=level,
        count=count,
        news_type=news_type
    )


@app.route('/learn', methods=['POST'])
def learn():
    level = request.form.get('cefr')
    count = int(request.form.get('count'))

    # the file received
    json_path = os.path.join('data/vocabulary', 'words.json')

    with open(json_path, 'r', encoding='utf-8') as f:
        words = json.load(f)

    # choose the number of voc 
    selected = words[:count]

    return render_template(
        'vocabulary.html', 
        words = selected,
        level = level,
        feedback = {}
    )




# use vocabulary make sentence
@app.route('/check_sentence', methods=['POST'])
def check_sentence():
    word = request.form.get('word')
    sentence = request.form.get('sentence')
    level = request.form.get('level')
    count = int(request.form.get('count'))

    # mock reply
    mock_result = {
        "word": word,
        "user_sentence": sentence,
        "is_correct": False if "bad" in sentence else True,
        "explanation": "Example, false if bad inside"
    }

    # load vocabulary
    json_path = os.path.join('data/vocabulary', 'words.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        all_words = json.load(f)

    words = all_words[:count]

    # not redirect, add anchor
    return render_template(
        'vocabulary.html',
        words=words,
        level=level,
        feedback={word: mock_result},
        anchor=word   # use for scroll 
    )


''' Cloze '''
@app.route('/cloze', methods=['GET'])
def cloze():
    # read voc
    with open('data/vocabulary/words.json', 'r', encoding='utf-8') as f:
        words = json.load(f)

    return render_template(
        'cloze.html',
        stage="select",
        words=words
    )

@app.route('/cloze_select', methods=['POST'])
def cloze_select():
    selected_words = request.form.getlist('words')

    data = [{"word": w} for w in selected_words]

    with open('data/cloze/input.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # show cloze article
    return redirect('/cloze_play')


@app.route('/cloze_play', methods=['GET'])
def cloze_play():
    # read test.txt
    with open('data/cloze/test.txt', 'r', encoding='utf-8') as f:
        text = f.read()

    # read input.json
    with open('data/cloze/input.json', 'r', encoding='utf-8') as f:
        selected_words = json.load(f)

    def replace_blank(match):
        idx = match.group(1)
        return f'<input type="text" name="blank_{idx}" style="width:120px;">'

    html_text = re.sub(r'___\[(\d+)\]___', replace_blank, text)

    return render_template(
        'cloze.html',
        stage="play",
        cloze_text=html_text,
        selected_words=selected_words,
        result=None
    )




@app.route('/submit_cloze', methods=['POST'])
def submit_cloze():
    # read answer
    with open('data/cloze/answer.txt', 'r', encoding='utf-8') as f:
        answers = json.load(f)

    # read voc chosen by user
    with open('data/cloze/input.json', 'r', encoding='utf-8') as f:
        selected_words = json.load(f)

    used_words = set(request.form.getlist('used_word'))

    result = {}

    for key, value in request.form.items():
        idx = key.replace('blank_', '')
        user = value.strip()
        correct = answers.get(idx, "")

        is_correct = user.lower() == correct.lower()
        result[idx] = {
            "user": user,
            "correct": correct,
            "is_correct": user.lower() == correct.lower()
        }
        if is_correct and correct:
            used_words.add(correct)

    # re-read test.txt
    with open('data/cloze/test.txt', 'r', encoding='utf-8') as f:
        text = f.read()

    def replace_blank(match):
        idx = match.group(1)
        r = result.get(idx)

        if not r:
            return f'<input type="text" name="blank_{idx}" style="width:120px;">'

        color = "#c8f7c5" if r["is_correct"] else "#f7c5c5"
        readonly = "readonly" if r["is_correct"] else ""
        return f'''
        <input type="text"
               name="blank_{idx}"
               value="{r['user']}"
               {readonly}
               style="width:120px; background-color:{color};">
        '''
    locked_words = set()

    for idx, r in result.items():
        if r["is_correct"]:
            locked_words.add(r["correct"])



    html_text = re.sub(r'___\[(\d+)\]___', replace_blank, text)
    

    return render_template(
        'cloze.html',
        stage="play",
        cloze_text=html_text,
        selected_words=selected_words,
        used_words=list(used_words),
        locked_words=locked_words,
        result=result
    )








if __name__ == '__main__':
    app.run(debug=True)
