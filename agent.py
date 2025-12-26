import os, logging, json, requests

logger = logging.getLogger(__name__)

class Agent:
    """
    一個跟 LLM API 溝通的 Agent
    
    功能:
        - 根據英文新聞文章, 整理出符合 CEFR 等級的單字表
        - 檢查使用者造句時, 單字是否使用正確
        - 根據使用者選擇的單字生成一篇短文, 作為克漏字題目
        - 為 hangman 遊戲產生英文提示句
    """
    DEFAULT_API_URL = "https://api-gateway.netdb.csie.ncku.edu.tw/api/chat"
    NEWS_VOC_SCHEMA = {     # 整理新聞單字的 JSON Schema
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "word": {"type": "string"},
                "part_of_speech": {"type": "string"},
                "zh-Hant_definition": {"type": "string"},
                "example_sentence": {"type": "string"},
            },
            "required": ["word", "part_of_speech", "zh-Hant_definition", "example_sentence"],
        },
    }
    CHECK_VOC_SCHEMA = {    # 檢查單字使用正確性的 JSON Schema
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "word": {"type": "string"},
                "is_correct": {"type": "boolean"},
                "explanation": {"type": "string"},
            },
            "required": ["word", "is_correct", "explanation"],
        },
    }
    MIND_MAP_SCHEMA = {     # 心智圖的 JSON Schema
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "The id of the root node, e.g. 'root'"
            },
            "text": {
                "type": "string",
                "description": "The text of the root node"
            },
            "children": {
                "type": "array",
                "description": "The child nodes of this node",
                "items": { "$ref": "#/definitions/node" },
                "default": []
            }
        },
        "required": ["id", "text", "children"],
        "additionalProperties": False,

        "definitions": {
            "node": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The id of the node. e.g., n1, n1-1"
                    },
                    "text": {
                        "type": "string",
                        "description": "The text of the node"
                    },
                    "children": {
                        "type": "array",
                        "description": "The child nodes of this node",
                        "items": { "$ref": "#/definitions/node" },
                        "default": []
                    }
                },
                "required": ["id", "text", "children"],
                "additionalProperties": False
            }
        }
    }
    READING_QUIZ_SCHEMA = { # 閱讀測驗的 JSON Schema
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string"
                },
                "type": {
                    "type": "string",
                    "enum": ["Multiple_Answer", "True_Or_False"]
                },
                "question": {
                    "type": "string"
                },
                "choices": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "minItems": 2
                },
                "correct_choices": {
                    "type": "array",
                    "items": {
                        "type": "integer",
                        "minimum": 0
                    },
                    "minItems": 1
                },
                "answer": {
                    "type": "boolean"
                },
                "explanation": {
                    "type": "string"
                }
            },
            "required": ["type", "question"],

            "oneOf": [
                {
                    "properties": {
                        "type": {"const": "Multiple_Answer"}
                    },
                    "required": ["choices", "correct_choices"]
                },
                {
                    "properties": {
                        "type": {"const": "True_Or_False"}
                    },
                    "required": ["answer"]
                }
            ],
            "additionalProperties": False
        }
    }


    def __init__(self, api_url = None, api_key = None, model = "gpt-oss:120b", timeout = 30):
        """
        初始化 Agent

        :param api_url: API 網址, 預設用 DEFAULT_API_URL
        :param api_key: API key, 預設從環境變數 OLLAMA_API_KEY 讀
        :param model: 要呼叫的模型名稱
        :param timeout: requests read timeout (秒)
        """
        self.api_url = api_url or self.DEFAULT_API_URL
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY")
        if not self.api_key:
            raise RuntimeError("Type the command in terminal: export OLLAMA_API_KEY={老師給的 key}")
        
        self.model = model
        self.timeout = timeout
    
    @staticmethod
    def _extract_json(msg):
        """
        從 LLM 回覆中擷取 ```json ... ``` 區塊並解析
        若找不到 code block, 嘗試直接把整段 msg 當作 JSON
        
        :param msg: 要解析的訊息 (string)
        :return: 解析後的 JSON 物件, 失敗回傳 None
        """
        start = msg.find("```json")
        if start == -1:
            # 沒有 markdown block, 就嘗試直接把整段 msg 當成 JSON
            try:
                return json.loads(msg)
            except json.JSONDecodeError:
                logger.exception("Failed to decode JSON from raw content")
                return None
            finally:
                logger.debug("_extract_json() finished for raw content")

        start += len("```json")
        end = msg.rfind("```")
        if end == -1 or end <= start:
            logger.error("Cannot find closing ``` for json block")
            return None

        json_str = msg[start:end].strip()
        try:
            data = json.loads(json_str)
            return data
        except json.JSONDecodeError:
            logger.exception("Failed to decode JSON from markdown block")
            return None
        finally:
            logger.debug("_extract_json() finished for markdown block")
        
    def _build_headers(self):
        """建立 HTTP headers """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        return headers

    def _chat(self, messages, stream = False):
        """
        實際發 HTTP POST 給 LLM API

        :param messages: 傳給 LLM 的訊息 list, 格式為 {"role": ..., "content": ...}
        :return: requests.Response 或 None (失敗時)
        """

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }

        response = None
        try:
            # 為了避免 log 太長，只顯示前 100 個字
            debug_payload = json.dumps(payload, ensure_ascii=False)[:100]
            logger.debug(f"Sending request to {self.api_url} with payload: {debug_payload}")

            response = requests.post(
                self.api_url, 
                headers=self._build_headers(), 
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.Timeout:
            logger.exception("Request timeout when calling %s", self.api_url)
            return None
        except requests.RequestException as e:
            logger.exception(f"Request failed: {e}")
        else:
            logger.info(f"Request success: status={response.status_code}")
            return response
        finally:
            logger.debug(f"chat() finished for messages count={len(messages)}")

    def _parse_response(self, response):
        """
        解析 API 回傳的 JSON, 取出 message.content 純文字

        :param response: requests.Response 物件
        :return: message.content 字串, 失敗回傳 None
        """
        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.exception("Failed to parse JSON response")
            return None
        finally:
            logger.debug(f"_parse_response() finished for response status={response.status_code}")

        if not isinstance(data, dict):
            logger.error("Unexpected JSON type (not dict)")
            return None
        
        msg = data.get("message")
        if not isinstance(msg, dict):
            logger.error("Missing or invalid 'message' field in response JSON")
            return None
        
        content = msg.get("content")
        if not isinstance(content, str):
            logger.error("Missing or invalid 'content' field in message")
            return None

        return content

    # ------------ 對外 API ------------
    def chat_with_prompt(self, prompt, stream = False, parse_json=True):
        """
        使用給定的 prompt 與 LLM 互動

        :param prompt: 要給 LLM 的內容 (string)
        :param stream: 是否使用 stream 模式
        :param parse_json: 是否要把回覆解析成 JSON 物件
        :return: 回覆的純文字 (string) 或 JSON 物件, 失敗回傳 None
        """
        if not prompt:
            logger.warning("Empty prompt, skip calling API")
            return None
        
        messages = [
            {"role": "user", "content": prompt},
        ]
        response = self._chat(messages, stream=stream)

        if response is None:
            return None
        
        content = self._parse_response(response)
        if content is None:
            return None

        if not parse_json:
            # 預設: 只回傳純文字
            return content
        # 需要 JSON 的: 整理新聞單字、檢查單字使用正確性
        return self._extract_json(content)

    def generate_prompt_of_voc(self, text_for_llm, CEFR = "B2", voc_numbers = 10):
        """
        產生要給 LLM 的內容: 整理英文新聞的單字
        
        :param text_for_llm: 從爬蟲取得的文章內容
        :param CEFR: 使用者輸入的 CEFR 等級, 預設 B2
        :param voc_numbers: 使用者希望要產生的單字數量, 預設 10
        :return: prompt 字串 
        """
        if not text_for_llm.strip():
            logger.warning(f"Text for LLM is empty, skip")
            return None
        
        schema_str = json.dumps(self.NEWS_VOC_SCHEMA, indent=2, ensure_ascii=False)

        prompt = (
            text_for_llm
            + f"\n\n根據這段英文文章，依據 CEFR={CEFR} 整理出 {voc_numbers} 個單字，"
            + "要不多不少剛剛好的數量，如果不夠的話請往低一階的程度找。"
            "輸出格式為 JSON 陣列，其 JSON Schema 如下：\n"
            "```json\n"
            + schema_str
            + "\n```\n"
            "請輸出一個完全符合上述 JSON Schema 的 JSON，"
            "整段回答必須被 ```json 與 ``` 包起來，且不要加入任何額外說明文字。"
        )
        return prompt
    
    def generate_prompt_of_check_voc(self, word_list, sentences_list):
        """
        產生要給 LLM 的內容: 檢查單字使用正確性
        
        :param word_list: 要檢查的單字 list
        :param sentences_list: 使用這些單字造的句子 list
        :return: prompt 字串
        """
        if not word_list or not sentences_list:
            logger.warning(f"The word list or sentences list is empty, skip")
            return None
        
        if len(word_list) != len(sentences_list):
            logger.warning("The length of word list and sentences list do not match, skip")
            return None
        
        schema_str = json.dumps(self.CHECK_VOC_SCHEMA, indent=2, ensure_ascii=False)
        prompt = (
            "請幫我檢查以下英文句子中，指定的單字是否有被正確使用，並且用繁體中文說明原因。\n"
            "以下是要檢查的資料（索引對應）：\n\n"
            f"word_list = {json.dumps(word_list, ensure_ascii=False)}\n"
            f"sentences_list = {json.dumps(sentences_list, ensure_ascii=False)}\n\n"
            "輸出格式為 JSON 陣列，其 JSON Schema 如下：\n"
            "```json\n"
            + schema_str
            + "```\n\n"
            "整段回答必須被 ```json 與 ``` 包起來，且不要加入任何額外說明文字"
        )
        return prompt
    
    def generate_prompt_of_cloze_test(self, word_list, CEFR = "B2"):
        """
        產生要給 LLM 的內容: 根據單字產生一篇小文章, 作為克漏字測驗用
        
        :param word_list: 要用來造句的單字 list
        :param CEFR: 使用者輸入的 CEFR 等級, 預設 B2
        :return: prompt 字串
        """
        if not word_list:
            logger.warning(f"The word list is empty, skip")
            return None
        
        prompt = (
            "請根據以下單字清單，寫一篇包含這些單字的英文短文，"
            "並且每個單字都要出現一次，且只能出現一次。\n"
            f"難度請符合 CEFR 等級：{CEFR}。\n"
            "回覆請使用純文字英文，不要加上任何說明、標題或 markdown 格式。\n\n"
            f"單字清單: {json.dumps(word_list, ensure_ascii=False)}"
        )
        return prompt

    def generate_prompt_of_describe_word(self, word, CEFR = "B2"):
        """
        產生要給 LLM 的內容: hangman 遊戲中的提示, 用英文描述單字
        
        :param word: 要描述的單字
        :param CEFR: 使用者輸入的 CEFR 等級, 預設 B2
        :return:  prompt 字串
        """
        if not word:
            logger.warning(f"The word is empty, skip")
            return None
        
        prompt = (
            f"請給我一段用英文描述單字 '{word}' 的句子，"
            f"描述內容請符合 CEFR={CEFR}，"
            "但不能直接提到這個單字本身，也不能提到它的任何詞形變化。"
            "回覆請使用純文字英文，不要加上任何說明、標題或 markdown 格式。"
        )
        return prompt
    
    def generate_prompt_of_mind_map(self, article):
        """
        產生要給 LLM 的內容: 新聞文章的心智圖
        
        :param article: 要產生心智圖的新聞
        :return: prompt 字串
        """
        if not article:
            logger.warning("The article is empty, skip")
            return None
        
        schema_str = json.dumps(self.MIND_MAP_SCHEMA, indent=2, ensure_ascii=False)

        prompt = (
            article
            + "\n\n根據這段英文文章，生成相符合的英文心智圖結構"
            + "\n- root 節點代表文章主題"
            + "\n- children 中的每一個節點代表主題的主要分支"
            + "\n- 每一個主要分支的 children 再拆成次分支"
            + "\n- 如果有需要，也可以再往下展開第 3 層或第 4 層"
            + "輸出格式為 JSON 陣列，其 JSON Schema 如下：\n"
            "```json\n"
            + schema_str
            + "\n```\n"
            "請輸出一個完全符合上述 JSON Schema 的 JSON，"
            "整段回答必須被 ```json 與 ``` 包起來，且不要加入任何額外說明文字。"
        )
        return prompt
    
    def generate_prompt_of_reading_quiz(self, article):
        """
        產生要給 LLM 的內容: 新聞文章的心智圖
        
        :param article: 要產生心智圖的新聞
        :return: prompt 字串
        """
        if not article:
            logger.warning("The article is empty, skip")
            return None
        
        schema_str = json.dumps(self.READING_QUIZ_SCHEMA, indent=2, ensure_ascii=False)

        prompt = (
            article
            + "\n\n根據這段英文文章，生成相對應的英文閱讀測驗"
            + "題目類型為 Multiple_Answer 或 True_Or_False，總共 5 題"
            + "輸出格式為 JSON 陣列，其 JSON Schema 如下：\n"
            "```json\n"
            + schema_str
            + "\n```\n"
            "請輸出一個完全符合上述 JSON Schema 的 JSON，"
            "整段回答必須被 ```json 與 ``` 包起來，且不要加入任何額外說明文字。"
        )
        return prompt
    
