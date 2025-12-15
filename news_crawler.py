import requests, random, logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

class BBCNewsCrawler:
    """
    用來爬取 BBC 不同類別的新聞

    功能:
        - 依據分類名稱 (news / business / arts / sport 等) 抓取首頁上的文章連結
        - 過濾掉影片與 live 連結
        - 解析文章頁面，擷取主要內文段落文字
    """

    BASE_URL = "https://www.bbc.com"
    # section id
    STYLE_SECTION_ID = {
        "news_style": "virginia-section-8",  # Business / News / Innovation
        "culture_style": "alaska-grid",      # Culture / Arts / Travel / Future-planet
    }
    
    # 類別對應設定: name -> (path, style)
    CATEGORY_CONFIG = {
        "news":          ("news",          "news_style"),
        "business":      ("business",      "news_style"),
        "innovation":    ("innovation",    "news_style"),

        "culture":       ("culture",       "culture_style"),
        "arts":          ("arts",          "culture_style"),
        "travel":        ("travel",        "culture_style"),
        "earth":         ("future-planet", "culture_style"),

        "sport":         ("sport",         "sport"),
    }

    def __init__(self, timeout = 10):
        """
        初始化 BBCNewsCrawler

        :param timeout: requests timeout (秒)
        """
        self.timeout = timeout

    def _build_url(self, path):
        """
        根據傳入的 path 產生完整的 BBC URL。
        
        :param path: 要爬取的路徑（例如 "news", "business"）
        :return: 完整網址（例如 "https://www.bbc.com/news"）
        """
        return f"{self.BASE_URL}/{path}"

    def _get_soup(self, url):
        """
        對指定 URL 發送 GET 請求並回傳 BeautifulSoup 物件
        
        :param url: 爬取的連結
        :return: 解析後的 BeautifulSoup 物件, 若請求失敗則回傳 None
        """
        try:
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception(f"Request failed: {url}" )
            return None
        return BeautifulSoup(resp.text, "html.parser")

    def _is_useless_url(self, url):
        """
        判斷 URL 是否為影片或 live 頁面, 如果是就視為不需要的連結

        :param url: 要判斷的 URL
        :return: 若為影片或 live 連結則回傳 True, 否則回傳 False
        """
        path = urlparse(url).path
        return "/videos/" in path or "/live/" in path
    
    def _find_section(self, soup, section_testid):
        """
        根據 data-testid 在頁面中找到對應的 section 區塊

        :param soup: 文章或分類頁面的 BeautifulSoup 物件
        :param section_testid: data-testid 的值, 例如 "virginia-section-8"
        :return: 對應的 <div> 標籤 (section), 若找不到則為 None
        """
        return soup.find("div", attrs={"data-testid": section_testid})

    def _extract_internal_links(self, section):
        """
        從指定的 section 內, 抓出所有 data-testid="internal-link" 的 <a>,
        並過濾掉影片和live 連結

        :param section: 頁面中代表文章區的 <div> 區塊
        :return: 一組 (set) 整理好的完整文章 URL
        """
        links = set()

        for a in section.find_all("a", href=True):
            if a.get("data-testid") != "internal-link":
                continue

            full_url = urljoin(self.BASE_URL, a["href"])
            if self._is_useless_url(full_url):
                continue

            links.add(full_url)

        return links

    def _parse_grid_page(self, soup, style):
        """
        解析 news_style / culture_style 類型的分類頁, 抓出文章連結

        :param soup: 分類頁面的 BeautifulSoup 物件
        :param style: 分類頁的類型 (news_style 或 culture_style)
        :return: 一組文章 URL, 若找不到對應 section 則回傳空集合
        """
        section_id = self.STYLE_SECTION_ID.get(style)
        if not section_id:
            raise ValueError(f"Unknown grid style: {style}")

        section = self._find_section(soup, section_id)
        if section is None:
            logger.warning(f"Section not found: data-testid={section_id}")
            return set()

        return self._extract_internal_links(section)
    
    def _parse_sport_page(self, soup):
        """
        解析 sport 類型的分類頁, 抓出 sport 類文章連結

        :param soup: sport 分類頁的 BeautifulSoup 物件
        :return: 一組文章 URL, 若找不到則回傳空的 set
        """
        links = set()

        # 限定要抓的範圍
        container = soup.select_one("ul.ssrcss-uy86gw-Grid.e12imr580")
        if container is None:
            logger.warning("Sport grid container not found")
            return links
        
        # 在 container 裡找連結
        promos = container.select('div[data-testid="promo"][type="article"]')

        for promo in promos:
            a = promo.select_one("h3 > a")
            if not a:
                continue

            full_url = urljoin(self.BASE_URL, a["href"])
            if self._is_useless_url(full_url):
                continue
            links.add(full_url)

        return links

    def _crawl_category(self, name):
        """
        根據傳入的新聞分類名稱, 抓取該分類首頁上的所有文章連結

        :param name: 分類名稱必須是 CATEGORY_CONFIG 的 key (例如 news, sport)
        :return: 一組文章 URL, 若抓取失敗則回傳空的 set
        """
        if name not in self.CATEGORY_CONFIG:
            raise ValueError(f"Unknown news type {name}")

        path, style = self.CATEGORY_CONFIG[name]
        url = self._build_url(path)
        soup = self._get_soup(url)
        if soup is None:
            return set()

        if style in ("news_style", "culture_style"):
            return self._parse_grid_page(soup, style)
        if style == "sport":
            return self._parse_sport_page(soup)

        raise ValueError(f"Cannot find the news style: {style}")

    def _extract_article_title(self, soup):
        """
        針對傳入的 Beautifulsoup 物件去解析出新聞標題
        
        :param soup: Beautifulsoup 物件
        :return: 新聞標題, 若找不到回傳空字串
        """
        header = soup.find("h1")
        if header is None:
            logger.warning("Cannot find the title")
            return ""
        title = header.get_text(" ", strip=True)
        return title
        
    def _extract_article_paragraphs(self, soup):
        """
        針對單一文章頁面的 BeautifulSoup 物件，抓取主要內文中的段落文字。

        只會擷取 data-component 為 "text-block" 或 "layout-block"
        底下的 <p> 文字, 並用換行符號拼接

        :param link: 文章的 URL
        :return: 文章內容文字（多個段落以 '\n' 分隔）, 若抓取失敗則回傳空字串
        """
        paragraphs = []
        for p in soup.find_all("p"):
            parent_block = p.find_parent(
                "div",
                attrs = {"data-component": ["text-block", "layout-block"]},
            )
            if not parent_block:
                continue
            text = p.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)

        return "\n".join(paragraphs) 
    
    def get_articles_by_category(self, name):
        """
        給定一個分類名稱, 抓取該分類所有文章並回傳其標題、內容與連結

        :param name: 分類名稱必須是 CATEGORY_CONFIG 的 key
        :return: dict 格式
            {
                "category": <str>,
                "articles": [
                    {
                        "id": <int>,       # 1-based index
                        "title": <str>,    # 文章標題，找不到則為空字串
                        "link": <str>,     # 文章 URL
                        "content": <str>,  # 文章內文，抓不到或為空則跳過該篇
                    },
                    ...
                ]
            }
            如果該分類完全抓不到任何連結，回傳 None
        """
        links = self._crawl_category(name)
        logger.info(f"[{name}] finds {len(links)} links")

        if not links:
            logger.warning(f"[{name}] does not find any links")
            return None
        
        articles = []
        for index, link in enumerate(links):
            soup = self._get_soup(link)
            if soup is None:
                logger.warning(f"[{name}] fail to fetch HTML of {link}")
                continue
            
            title = self._extract_article_title(soup)
            article_text = self._extract_article_paragraphs(soup)

            if not article_text.strip():
                logger.warning(f"[{name}] is empty article text")
                continue
            
            articles.append({
                "id": index + 1,
                "title": title,
                "link": link,
                "content": article_text,
            })
        if not articles:
            # 全部都失敗或沒有內容
            logger.warning(f"[{name}] no article with valid content")
            return None

        return {
            "category": name,
            "articles": articles,
        }
