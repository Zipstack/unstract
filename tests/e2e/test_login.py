from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


class TestLogin:
    def setup_method(self, method):
        options = Options()
        options.add_argument("--headless=new")
        self.driver = webdriver.Chrome(options=options)

    def teardown_method(self, method):
        self.driver.quit()

    def _check_page_load(self):
        try:
            self.driver.get("http://frontend.unstract.localhost")
        except Exception as e:
            print(f"Page load exception: {e}")
            return False
        else:
            return True

    def test_login(self):
        WebDriverWait(self.driver, timeout=30, poll_frequency=2).until(
            lambda _: self._check_page_load(),
            "Page load failed",
        )
        self.driver.implicitly_wait(0.5)
        self.driver.set_window_size(960, 615)
        # 3 | click | css=span |
        self.driver.find_element(By.CSS_SELECTOR, "button").click()
        # 4 | click | id=username |
        self.driver.find_element(By.ID, "username").click()
        # 5 | type | id=username | unstract
        self.driver.find_element(By.ID, "username").send_keys("unstract")
        # 6 | type | id=password | unstract
        self.driver.find_element(By.ID, "password").send_keys("unstract")
        # 7 | click | css=input:nth-child(11) |
        self.driver.find_element(By.CSS_SELECTOR, "input:nth-child(11)").click()
        WebDriverWait(self.driver, timeout=5).until(
            lambda _: self.driver.current_url.endswith("/mock_org/onboard"),
            "Login failed.",
        )
        self.driver.close()
