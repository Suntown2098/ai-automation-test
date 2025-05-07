import textwrap
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from src.config import SYSTEM_PROMPT, MARKDOWN_INPUT, USER_PROMPT

class SeleniumUtils:
    DRIVER_TIMEOUT_SECONDS = 120
    EMPTY_HTML_DOCUMENT = "<html><head></head><body></body></html>"

    def __init__(self):
        self.driver = self._initialize_driver()
        self.url = None

    def _initialize_driver(self):
        driver = webdriver.Chrome(options=Options())
        driver.set_window_size(1920, 1080)
        driver.implicitly_wait(self.DRIVER_TIMEOUT_SECONDS)
        return driver

    def _load_initial_page(self):
        try:
            self.driver.get(self.url)
        except WebDriverException:
            raise Exception(f"URL '{self.url}' is not reachable.")
        if self.driver.page_source == self.EMPTY_HTML_DOCUMENT:
            raise Exception(f"URL '{self.url}' is not reachable.")

    def connect_driver(self, url):
        self.url = url
        try:
            self._load_initial_page()
        except Exception as e:
            if self.driver:
                print("SeleniumUtils.connect_driver -> Disconnecting driver")
                self.driver.quit()
            raise e

    def close_local_driver(self):
        if self.driver is None:
            print("SeleniumUtils.close_local_driver -> The driver is already closed.")
        else:
            self.driver.quit()
            self.driver = None

    def go_to_url(self, url):
        self.url = url
        self._load_initial_page()

    def _assert_css_selector_exists(self, action):
        if action.css_selector is None:
            raise Exception("Action cannot be executed without a CSS selector")

    def _click_element(self, css_selector):
        try:
            self.driver.find_element(By.CSS_SELECTOR, css_selector).click()
            print("SeleniumUtils._click_element -> css id: " + css_selector)
        except:
            raise NoSuchElementException("SELENIUM: Could not click on the element with the CSS id: " + css_selector)

    def _enter_text_in_element(self, css_selector, text):
        try:
            element = self.driver.find_element(By.CSS_SELECTOR, css_selector)
            element.send_keys(text)
            print("SeleniumUtils._enter_text_in_element -> css id: " + css_selector)
        except:
            raise NoSuchElementException("SELENIUM: Could not enter text in the element with the CSS id: " + css_selector)

    def execute_action_for_prompt(self, content) -> bool:
        try:
            if content.action == "click":
                self._assert_css_selector_exists(content)
                self._click_element(content.css_selector)

            elif content.action == "enter_text":
                self._assert_css_selector_exists(content)
                self._enter_text_in_element(content.css_selector, content.text)

            elif content.action == "key_enter":
                actions = ActionChains(self.driver)
                actions.send_keys(Keys.ENTER).perform()

            elif content.action == "scroll":
                self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)

            elif content.action == "finish":
                return False

            return True

        except NoSuchElementException as ex:
            print(f"SeleniumUtils.execute_action_for_prompt -> Failed to find element {content.css_selector}: {ex}")
            raise Exception("Failed to execute action, Generative AI returned invalid action")
        except Exception as ex:
            print(f"SeleniumUtils.execute_action_for_prompt -> Failed to execute prompt action: {ex}")
            raise Exception("Failed to execute action generative AI action")

    def assign_auto_generated_ids(self):
        js_script = textwrap.dedent("""
                function generateUniqueId(index) {
                    var now = new Date();
                    var timestamp = now.getMinutes().toString() + now.getSeconds().toString();
                    return "idTUp" + index + "T" + timestamp;
                }

                const elements = document.querySelectorAll('li, button, input, textarea, [type=text], a');
                elements.forEach((el, index) => {
                    if (!el.id) {
                        el.id = generateUniqueId(index);
                    }
                });    
                """).strip()

        self.driver.execute_script(js_script)

    def get_visible_dom(self):
        js_script = textwrap.dedent("""

                function isElementInViewport(el) {
                    var rect = el.getBoundingClientRect();
                    return (
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                    );
                }

                function isElementVisible(el) {
                    return el.offsetWidth > 0 && el.offsetHeight > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                }


                var allElements = document.querySelectorAll('body *');
                var visibleElements = Array.from(allElements)
                    .filter(el => isElementInViewport(el) && isElementVisible(el));

                // Filter out child elements
                var filteredElements = visibleElements.filter(el => {
                    return !visibleElements.some(parentEl => parentEl !== el && parentEl.contains(el));
                });

                var visibleElementsHtml = filteredElements.map(el => el.outerHTML).join('\\n');
                return visibleElementsHtml;

                """).strip()

        return str(self.driver.execute_script(js_script))
