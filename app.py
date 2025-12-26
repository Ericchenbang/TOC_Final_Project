from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import json
import os
import re
import random
import logging

from english_learning_service import EnglishLearningService

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(
    level=logging.INFO, # DEBUG
    format=LOG_FORMAT,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "hangman-secret-key"

# root directory
@app.route('/')
def index():
    return render_template('index.html')
    
#--------------------------------------------------------------#
#--------------------------------------------------------------#

# watch news
@app.route('/news', methods=['POST'])
def news():
    category = request.form.get('news_type')
    output_path = f"data/news/{category}.json"

    service = EnglishLearningService()
    success = service.get_news_by_category(
        category=category,
        output_path=output_path
    )

    if success is True:
        return redirect(url_for('news_list', category=category))
    else:
        return "Failed to fetch news", 500

@app.route('/news_list/<category>')
def news_list(category):
    news_path = f"data/news/{category}.json"

    with open(news_path, 'r', encoding='utf-8') as f:
        news_data = json.load(f)

    return render_template(
        'news_list.html',
        category=category,
        articles=news_data["articles"]
    )


@app.route('/news_detail/<category>/<int:article_id>')
def news_detail(category, article_id):
    news_path = f"data/news/{category}.json"

    with open(news_path, 'r', encoding='utf-8') as f:
        news_data = json.load(f)

    # find coresponding id article
    article = next(
        (a for a in news_data["articles"] if a["id"] == article_id),
        None
    )

    if article is None:
        return "Article not found", 404

    session['current_article_category'] = category
    session['current_article_id'] = article_id
    session['current_article_text'] = article['content']
    session['current_article_title'] = article.get('title')

    return render_template(
        'news_detail.html',
        category=category,
        article=article
    )

#--------------------------------------------------------------#
#--------------------------------------------------------------#
@app.route('/generate_mindmap', methods=['POST'])
def generate_mindmap_route():
    category = session.get('current_article_category')
    article_id = session.get('current_article_id')
    article_text = session.get('current_article_text')

    if not category:
        flash('Invalid state of article, please re-choose category of news :<', 'warning')
        return redirect(url_for('index'))

    
    if not article_id or not article_text:
        flash('Please goto news again to generate mindmap~', 'warning')
        return redirect(url_for('news_list', category=category))
    
    
    if session.get('mindmap_article_id') == article_id \
       and os.path.exists('data/mindMap.json'):
        return redirect(url_for('mindmap'))

    try:
        service = EnglishLearningService()
        service.generate_mind_map(
            article_text,
            output_path='data/mindMap.json'
        )
        session['mindmap_article_id'] = article_id
        return redirect(url_for('mindmap'))

    except Exception as e:
        print('[MindMap Error]', e)
        flash('Fail to generate mindmap, please try again', 'error')
        return redirect(url_for('news_list', category=category))
    

@app.route('/mindmap')
def mindmap():
    with open('data/mindMap.json', 'r', encoding='utf-8') as f:
        mindmap_data = json.load(f)

    return render_template(
        'mindmap.html',
        mindmap=mindmap_data
    )

#--------------------------------------------------------------#
#--------------------------------------------------------------#
@app.route('/generate_reading', methods=['POST'])
def generate_reading_route():
    category = session.get('current_article_category')
    article_id = session.get('current_article_id')
    article_text = session.get('current_article_text')
    
    if not category:
        flash('Invalid state of article, please re-choose category of news', 'warning')
        return redirect(url_for('index'))

    
    if not article_id or not article_text:
        flash('Please goto news again to generate reading test ~', 'warning')
        return redirect(url_for('news_list', category=category))

    
    if session.get('reading_article_id') == article_id \
       and os.path.exists('data/reading.json'):
        return redirect(url_for('reading'))

    service = EnglishLearningService()
    service.generate_reading_quiz(
        article_text,
        output_path='data/reading.json'
    )
    session['reading_article_id'] = article_id
    return redirect(url_for('reading'))

@app.route('/reading', methods=['GET'])
def reading():
    with open('data/reading.json', 'r', encoding='utf-8') as f:
        questions = json.load(f)

    return render_template(
        'reading.html',
        questions=questions,
        result=None
    )

@app.route('/submit_reading', methods=['POST'])
def submit_reading():
    with open('data/reading.json', 'r', encoding='utf-8') as f:
        questions = json.load(f)
        
    for idx, q in enumerate(questions):
        qid = q.get("id", f"q_{idx}")

        if q["type"] == "True_Or_False":
            if request.form.get(qid) is None:
                return redirect(url_for('reading'))

        else:  # Multiple_Answer
            if not request.form.getlist(qid):
                return redirect(url_for('reading'))

    result = {}
    for idx, q in enumerate(questions):
        qid = q.get("id", f"q_{idx}")

        if q["type"] == "True_Or_False":
            user_answer = request.form.get(qid)
            correct = str(q["answer"]).lower()

            is_correct = (user_answer == correct)

            result[qid] = {
                "type": q["type"],
                "user": user_answer,
                "is_correct": is_correct,
                "explanation": q["explanation"]
            }

        else:  # Multiple_Answer
            user_choices = request.form.getlist(qid)
            correct_choices = [str(i) for i in q["correct_choices"]]

            is_correct = sorted(user_choices) == sorted(correct_choices)

            result[qid] = {
                "type": q["type"],
                "user": user_choices,
                "correct": correct_choices,
                "is_correct": is_correct,
                "explanation": q["explanation"]
            }

    return render_template(
        'reading.html',
        questions=questions,
        result=result
    )



#--------------------------------------------------------------#
#--------------------------------------------------------------#
@app.route('/start_learn', methods=['POST'])
def start_learn():
    category = request.form.get('category')
    article_id = int(request.form.get('article_id'))
    cefr = request.form.get('cefr')
    count = int(request.form.get('count'))
    session['cefr'] = request.form.get('cefr')
    session['count'] = int(request.form.get('count'))

    # read news file
    news_path = f"data/news/{category}.json"
    with open(news_path, 'r', encoding='utf-8') as f:
        news_data = json.load(f)

    article = next(
        (a for a in news_data["articles"] if a["id"] == article_id),
        None
    )

    if article is None:
        return "Article not found", 404

    article_content = article.get("content") or article.get("summary")
    if not article_content:
        return "Article content missing", 500

    # call LLM produce vocabulary
    service = EnglishLearningService()

    vocab_path = "data/vocabulary/words.json"

    success = service.get_vocabulary_from_news(
        article_content=article_content,
        CEFR=cefr,
        n_words=count,
        output_path=vocab_path
    )

    if success is not True:
        return "Failed to generate vocabulary", 500

    return redirect(url_for('learn'))




@app.route('/learn', methods=['GET'])
def learn():
    level = session.get('cefr')
    count = session.get('count')

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


#--------------------------------------------------------------#
#--------------------------------------------------------------#

# use vocabulary make sentence
@app.route('/check_sentence', methods=['POST'])
def check_sentence():
    word = request.form.get('word')
    sentence = request.form.get('sentence')
    level = request.form.get('level')
    count = int(request.form.get('count'))

    service = EnglishLearningService()
    result_path = "data/vocabulary/sentence_feedback.json"
    success = service.check_vocabulary_usage(
        word_list=[word],
        sentences=[sentence],
        output_path=result_path
    )

    if success is not True:
        return "LLM sentence check failed", 500
    
    # read LLM feedback
    with open(result_path, 'r', encoding='utf-8') as f:
        resp = json.load(f)

    feedback_result = {
        "word": word,
        "user_sentence": sentence,
        "is_correct": resp[0].get("is_correct"),
        "explanation": resp[0].get("explanation")
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
        feedback={word: feedback_result},
        anchor=word   # use for scroll 
    )

#--------------------------------------------------------------#
#--------------------------------------------------------------#

# Cloze 
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

    # if user choose less than 2
    if len(selected_words) < 2:
        with open('data/vocabulary/words.json', 'r', encoding='utf-8') as f:
            words = json.load(f)

        return render_template(
            'cloze.html',
            stage="select",
            words=words,
            error="Please select at least TWO words to start the cloze test."
        )

    data = [{"word": w} for w in selected_words]

    with open('data/cloze/input.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    service = EnglishLearningService();
    level = session.get('cefr')
    output_path = "data/cloze/cloze.json"
    success = service.generate_cloze_test(
        word_list=selected_words,
        CEFR=level,
        output_path=output_path
    )
    if not success:
        return "Failed to generate cloze test", 500

    # show cloze article
    return redirect('/cloze_play')


@app.route('/cloze_play', methods=['GET'])
def cloze_play():
    # read cloze json
    with open('data/cloze/cloze.json', 'r', encoding='utf-8') as f:
        cloze_data = json.load(f)

    text = cloze_data["question"]

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
    # read cloze json
    with open('data/cloze/cloze.json', 'r', encoding='utf-8') as f:
        cloze_data = json.load(f)

    text = cloze_data["question"]

    # turn ans list into dict: { "1": "reaction", ... }
    answers = {
        str(item["idx"]): item["word"]
        for item in cloze_data["ans"]
    }

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

    def replace_blank(match):
        idx = match.group(1)
        r = result.get(idx)

        if not r:
            return f'<input type="text" name="blank_{idx}" style="width:120px;">'

        # if correct，add readonly attribute and correct type
        if r["is_correct"]:
            return f'<input type="text" name="blank_{idx}" value="{r["user"]}" readonly class="cloze-input correct">'
        else:
            return f'<input type="text" name="blank_{idx}" value="{r["user"]}" class="cloze-input error">'

        color = "#c8f7c5" if r["is_correct"] else "#f7c5c5"
        readonly = "readonly" if r["is_correct"] else ""
        return f'''
        <input type="text"
               name="blank_{idx}"
               value="{r['user']}"
               {readonly}
               style="width:120px; background-color:{color};">
        '''
    locked_words = {
        r["correct"] for r in result.values() if r["is_correct"]
    }

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

#--------------------------------------------------------------#
#--------------------------------------------------------------#
## Hangman Game ###
@app.route('/hangman', methods=['GET'])
def hangman():
    # read vocabulary
    with open('data/vocabulary/words.json', 'r', encoding='utf-8') as f:
        words = json.load(f)

    answer = random.choice(words)["word"].lower()

    session["hangman_answer"] = answer
    session["hangman_guessed"] = []
    session["hangman_wrong"] = 0
    session["hangman_hint_used"] = False

    service = EnglishLearningService()

    level = session.get('cefr')
    output_path = "data/hangman/describe.txt"
    service.generate_hangman_hint(
        word=answer,
        CEFR=level,
        output_path=output_path
    )

    masked = " ".join("_" for _ in answer)

    return render_template(
        'hangman.html',
        masked=masked,
        guessed=[],
        wrong=0,
        win=False,
        lose=False
    )


@app.route('/hangman_guess_ajax', methods=['POST'])
def hangman_guess_ajax():
    data = request.json
    letter = data.get("letter", "").lower()

    answer = session.get("hangman_answer")
    guessed = session.get("hangman_guessed", [])
    wrong = session.get("hangman_wrong", 0)

    if not letter or len(letter) != 1 or not letter.isalpha():
        return jsonify({"error": "invalid input"})

    if letter not in guessed:
        guessed.append(letter)
        if letter not in answer:
            wrong += 1

    session["hangman_guessed"] = guessed
    session["hangman_wrong"] = wrong
    

    masked = " ".join(c if c in guessed else "_" for c in answer)

    win = "_" not in masked
    lose = wrong >= 6

    return jsonify({
        "masked": masked,
        "guessed": guessed,
        "wrong": wrong,
        "win": win,
        "lose": lose,
        "answer": answer if lose else None
    })


@app.route('/hangman_hint', methods=['POST'])
def hangman_hint():
    # The user had used the hint
    if session.get("hangman_hint_used"):
        return jsonify({
            "error": "hint_used",
            "wrong": session.get("hangman_wrong", 0)
        })

    # noted as used
    session["hangman_hint_used"] = True

    # minus one life
    wrong = session.get("hangman_wrong", 0) + 1
    session["hangman_wrong"] = wrong

    hint_path = 'data/hangman/describe.txt'
    if not os.path.exists(hint_path):
        return jsonify({
            "error": "hint_not_ready",
            "wrong": wrong
        })
    with open(hint_path, 'r', encoding='utf-8') as f:
        hint_text = f.read()
    
    
    lose = wrong >= 6

    return jsonify({
        "hint": hint_text,
        "wrong": wrong,
        "lose": lose
    })



if __name__ == '__main__':
    app.run(debug=True)
