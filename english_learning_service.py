import logging, json

from news_crawler import BBCNewsCrawler
from agent import Agent
from english_learning import EnglishLearning

logger = logging.getLogger(__name__)


class EnglishLearningService:
    """
    整合 BBCNewsCrawler、Agent、EnglishLearning, 對外提供一組乾淨的後端服務 API。
    """

    def __init__(self):
        self.crawler = BBCNewsCrawler()
        self.agent = Agent(timeout=120)
        self.english_learning = EnglishLearning()

    @staticmethod
    def _save_db(data, write_path):
        with open(write_path, "w", encoding="utf-8") as f:
            if isinstance(data, (dict, list)):
                json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                f.write(str(data))
        f.close()

    # ---------- 1. BBC 新聞相關 API ----------
    def get_news_by_category(self, category, output_path = None):
        """
        根據分類抓 BBC 新聞列表（只負責抓新聞，不處理單字）

        :param category: "news", "business", "sport", ...
        :return: 存到資料庫成功, 回傳 True, 反之回傳 False, 若資料有誤則回傳 None
        """
        try:
            if not category:
                logger.warning("get_news_by_category() got empty category")
                return None

            news = self.crawler.get_articles_by_category(category)
            if news is None:
                logger.error("crawler.get_articles_by_category() returned None")
                return None

            if "articles" not in news or not isinstance(news["articles"], list):
                logger.error("news format invalid: missing 'articles' or not list")
                return None

            if not news["articles"]:
                logger.warning("No articles in category=%s", category)
                return None

            # 資料存檔
            if output_path is None:
                logger.info("There is no output_path")
                return False
            else:
                self._save_db(news, output_path)
                return True
            
        except Exception:
            logger.exception("get_news_by_category(%r) failed", category)
            return None

    def get_vocabulary_from_news(self, article_content, CEFR, n_words, output_path = None):
        """
        給定一篇文章內容, 請 LLM 依據 CEFR 等級整理指定數量的單字

        :param article_content: 文章全文（純文字）
        :param CEFR: CEFR 等級, e.g., "B1"
        :param n_words: 要整理幾個單字
        :return: 存到資料庫成功, 回傳 True, 反之回傳 False, 若資料有誤則回傳 None
        """
        if not article_content or not article_content.strip():
            logger.warning("article_content is empty, skip calling LLM")
            return None

        try:
            # 產生 prompt
            prompt = self.agent.generate_prompt_of_voc(
                article_content,
                CEFR,
                n_words,
            )
            if not prompt:
                logger.error("Failed to build prompt for vocabulary")
                return None

            # 呼叫 LLM
            voc = self.agent.chat_with_prompt(
                prompt,
                stream=False,
                parse_json=True,
            )

            # 檢查回傳結果
            if voc is None:
                logger.error("LLM returned None when generating vocabulary")
                return None

            if not isinstance(voc, list):
                logger.error("Unexpected vocabulary format (not list): %r", voc)
                return None

            # 資料存檔
            if output_path is None:
                logger.info("There is no output_path")
                return False
            else:
                self._save_db(voc, output_path)
                return True
            
        except Exception:
            logger.exception("get_vocabulary_from_news() failed")
            return None

    # ---------- 2. 檢查單字用法 API ----------
    def check_vocabulary_usage(self, word_list, sentences, output_path = None):
        """
        檢查單字是否正確使用在句子裡

        :param word_list: 單字 list
        :param sentences: 句子 list (跟 word_list 一一對應)
        :return: 存到資料庫成功, 回傳 True, 反之回傳 False, 若資料有誤則回傳 None
        """
        if not word_list or not sentences:
            logger.warning("word_list or sentences is empty in check_vocabulary_usage()")
            return None

        if len(word_list) != len(sentences):
            logger.warning(
                "Length mismatch: word_list(%d) != sentences(%d)",
                len(word_list),
                len(sentences),
            )
            return None

        try:
            # 產生 prompt
            prompt = self.agent.generate_prompt_of_check_voc(word_list, sentences)
            if not prompt:
                logger.error("Failed to build prompt for check_vocabulary_usage")
                return None

            # 呼叫 LLM
            resp = self.agent.chat_with_prompt(
                prompt,
                stream=False,
                parse_json=True,
            )
            if resp is None:
                logger.error("API response is None in check_vocabulary_usage()")
                return None

            if not isinstance(resp, list):
                logger.error("Unexpected response format (not list): %r", resp)
                return None

            # 資料存檔
            if output_path is None:
                logger.info("There is no output_path")
                return False
            else:
                self._save_db(resp, output_path)
                return True
            
        except Exception:
            logger.exception("check_vocabulary_usage() failed")
            return None

    # ---------- 3. 克漏字 ----------
    def generate_cloze_test(self, word_list, CEFR, output_path = None):
        """
        生成一篇含有指定單字的文章，並用這些單字做克漏字

        :param word_list: 要挖空的單字清單
        :param CEFR: 文章難度
        :return: 存到資料庫成功, 回傳 True, 反之回傳 False, 若資料有誤則回傳 None
        """
        if not word_list:
            logger.warning("word_list is empty in generate_cloze_test()")
            return None

        try:
            prompt = self.agent.generate_prompt_of_cloze_test(word_list, CEFR)
            if not prompt:
                logger.error("Failed to build prompt for cloze test")
                return None
            
            original_text = self.agent.chat_with_prompt(
                prompt,
                stream=False,
                parse_json=False,
            )
            if not original_text:
                logger.error("LLM returned empty text for cloze test")
                return None

            result = self.english_learning.cloze_deletion(
                original_text,
                word_list,
            )
            
            # 資料存檔
            if output_path is None:
                logger.info("There is no output_path")
                return False
            else:
                self._save_db(result, output_path)
                return True
            
        except Exception:
            logger.exception("generate_cloze_test() failed")
            return None

    # ---------- 4. Hangman 提示 ----------
    def generate_hangman_hint(self, word, CEFR, output_path = None):
        """
        給定單字, 請 LLM 用英文描述（不直接說出單字）, 作為 Hangman 的提示

        :param word: 需要提示的單字
        :param CEFR: 英文等級
        :return: 存到資料庫成功, 回傳 True, 反之回傳 False, 若資料有誤則回傳 None
        """
        if not word:
            logger.warning("Empty word in generate_hangman_hint()")
            return None

        try:
            prompt = self.agent.generate_prompt_of_describe_word(word, CEFR)
            if not prompt:
                logger.error("Failed to build prompt for hangman hint")
                return None

            resp = self.agent.chat_with_prompt(
                prompt,
                stream=False,
                parse_json=False,
            )
            
            # 資料存檔
            if output_path is None:
                logger.info("There is no output_path")
                return False
            else:
                self._save_db(resp, output_path)
                return True
            
        except Exception:
            logger.exception("generate_hangman_hint() failed")
            return None

    # ---------- 5. 心智圖 ----------
    def generate_mind_map(self, article_text, output_path = None):
        """
        根據文章內容生成心智圖結構
        
        :param article_text: 做成心智圖的文章
        :return: 存到資料庫成功, 回傳 True, 反之回傳 False, 若資料有誤則回傳 None
        """
        if not article_text or not article_text.strip():
            logger.warning("Empty article_text in generate_mind_map()")
            return None

        try:
            prompt = self.agent.generate_prompt_of_mind_map(article_text)
            if not prompt:
                logger.error("Failed to build prompt for mind map")
                return None

            resp = self.agent.chat_with_prompt(
                prompt,
                stream=False,
                parse_json=True,
            )
            if resp is None:
                logger.error("LLM returned None in generate_mind_map()")
                return None

            if not isinstance(resp, dict):
                logger.error("Unexpected mind map format (not dict): %r", resp)
                return None

            # 資料存檔
            if output_path is None:
                logger.info("There is no output_path")
                return False
            else:
                self._save_db(resp, output_path)
                return True
            
        except Exception:
            logger.exception("generate_mind_map() failed")
            return None

    # ---------- 6. 閱讀測驗 ----------
    def generate_reading_quiz(self, article_text, output_path = None):
        """
        根據文章內容生成閱讀測驗題目
        
        :param article_text: 做成閱讀測驗的文章
        :return: 存到資料庫成功, 回傳 True, 反之回傳 False, 若資料有誤則回傳 None
        """
        if not article_text or not article_text.strip():
            logger.warning("Empty article_text in generate_reading_quiz()")
            return None

        try:
            prompt = self.agent.generate_prompt_of_reading_quiz(article_text)
            if not prompt:
                logger.error("Failed to build prompt for reading quiz")
                return None

            resp = self.agent.chat_with_prompt(
                prompt,
                stream=False,
                parse_json=True,
            )
            if resp is None:
                logger.error("LLM returned None in generate_reading_quiz()")
                return None

            if not isinstance(resp, list):
                logger.error("Unexpected reading quiz format (not list): %r", resp)
                return None

            # 資料存檔
            if output_path is None:
                logger.info("There is no output_path")
                return False
            else:
                self._save_db(resp, output_path)
                return True
            
        except Exception:
            logger.exception("generate_reading_quiz() failed")
            return None
