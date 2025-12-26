import re

class EnglishLearning:
    """
    提供英文學習的小工具

    功能:
        - 依指定單字在文章中挖空, 產生克漏字題目, 並檢查作答是否正確
    """
    
    def __init__(self):
        pass

    def cloze_deletion(self, text, words):
        """
        在 text 中, 對出現於 words 的單字挖空，替換為 ___[idx]___

        :return: (挖空後的新文章, 答案 list)
        """
        # 要匹配的單字格式不分大小寫
        pattern = re.compile(r"\b[a-zA-Z]+\b")
        target_set = {w.lower() for w in words}

        ans_list = []
        replace_span = []
        idx = 1

        for match_word in pattern.finditer(text):
            word = match_word.group(0)
            ans = word.lower()
            # 如果找到的單字不在指定單字清單中, 跳過
            if ans not in target_set:
                continue
            ans_list.append({'idx': idx, 'word': word})
            replace_span.append((match_word.start(), match_word.end(), idx))
            idx += 1
        
        new_text_parts = []
        pos = 0
        for start, end, i in replace_span:
            # 替換的單字前面的文字加進去
            if pos < start:
                new_text_parts.append(text[pos:start])

            # 把單字替換成填空
            new_text_parts.append(f"___[{i}]___")
            pos = end
            
        # 最後一個替換的單字後面的文字加進去
        if pos < len(text):
            new_text_parts.append(text[pos:])

        new_text_parts = "".join(new_text_parts)

        return {
            "question": new_text_parts, 
            "ans": ans_list
        }