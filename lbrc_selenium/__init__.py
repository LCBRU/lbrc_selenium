import os
import zipfile
import re
import smtplib
from time import sleep
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from urllib.parse import urljoin
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.encoders import encode_base64
from email.mime.text import MIMEText
from selenium.webdriver.support.ui import WebDriverWait


RE_REMOVE_HTML_TAGS = re.compile('<.*?>')


def get_selenium():
    args = dict(
        download_directory=os.environ["LBRC_SELENIUM_DOWNLOAD_DIRECTORY"],
        base_url=os.environ["LBRC_SELENIUM_BASE_URL"],
        implicit_wait_time=float(os.environ.get("LBRC_SELENIUM_IMPLICIT_WAIT_TIME", 1.0)),
        click_wait_time=float(os.environ.get("LBRC_SELENIUM_CLICK_WAIT_TIME", 1)),
        download_wait_time=float(os.environ.get("LBRC_SELENIUM_DOWNLOAD_WAIT_TIME", 30)),
        page_wait_time=float(os.environ.get("LBRC_SELENIUM_PAGE_WAIT_TIME", 5))
    )

    if os.environ.get("LBRC_SELENIUM_HOST", None):
        return SeleniumGridHelper(
            selenium_host=os.environ["LBRC_SELENIUM_HOST"],
            selenium_port=os.environ.get("LBRC_SELENIUM_PORT", '4444'),
            **args,
        )
    else:
        return SeleniumLocalHelper(
            headless=os.environ.get("LBRC_SELENIUM_HEADLESS", False),
            **args,
        )


class Selector:
    def __init__(self, query, by):
        self.query = query
        self.by = by

class CssSelector(Selector):
    def __init__(self, query):
        super().__init__(query, By.CSS_SELECTOR)

class XpathSelector(Selector):
    def __init__(self, query):
        super().__init__(query, By.XPATH)


class SeleniumHelper:
    def __init__(
        self,
        driver,
        download_directory,
        base_url,
        click_wait_time=0.2,
        download_wait_time=5,
        page_wait_time=1,
    ):
        self.click_wait_time = click_wait_time
        self.download_wait_time = download_wait_time
        self.page_wait_time = page_wait_time

        self.driver = driver

        self.base_url = base_url

        self.download_directory = Path(download_directory)
        self.download_directory.mkdir(parents=True, exist_ok=True)
        self._clear_directory(self.download_directory)


    def unzip_download_directory_contents(self):
        for zp in self._download_directory.iterdir():
            with zipfile.ZipFile(zp, "r") as zf:
                zf.extractall(self._download_directory)
    
    def _clear_directory(self, directory):
        for f in directory.iterdir():
            f.unlink()
    
    def get(self, url):
        self.driver.get(urljoin(self.base_url, url))
        self.wait_to_appear(CssSelector('body'))

    def convert_to_relative_url(self, url):
        if url.startswith(self.base_url):
            return url[len(self.base_url):]
        else:
            return url

    def wait_to_appear(self, selector, element=None, seconds_to_wait=10):
        return WebDriverWait((element or self.driver), seconds_to_wait).until(lambda x: x.find_element(selector.by, selector.query))
    
    def wait_to_disappear(self, selector, element=None, seconds_to_wait=10):
        return WebDriverWait((element or self.driver), seconds_to_wait).until_not(lambda x: x.find_element(selector.by, selector.query))
    
    def get_parent(self, element):
        return self.get_element(XpathSelector("./.."), element=element)
    
    def get_element(self, selector, allow_null=False, element=None):
        try:
            return (element or self.driver).find_element(selector.by, selector.query)

        except (NoSuchElementException, TimeoutException) as ex:
            if not allow_null:
                raise ex
    
    def get_elements(self, selector, element=None):
        return (element or self.driver).find_elements(selector.by, selector.query)
    
    def type_in_textbox(self, selector, text, element=None):
        e = self.get_element(selector, element=element)
        e.clear()
        e.send_keys(text)
        return e

    def click_element(self, selector, element=None):
        e = self.get_element(selector, element=element)
        e.click()
        sleep(self.click_wait_time)
        return e
    
    def click_all(self, selector, element=None):
        while True:
            element = self.get_element(selector, allow_null=True, element=element)

            if element is None:
                break
            
            element.click()
            sleep(self.click_wait_time)
    
    def get_text(self, element):
        result = self.normalise_text(element.text)

        if len(result) == 0:
            result = self.normalise_text(element.get_attribute("text"))

            if len(result) == 0:
                result = self.get_innerHtml(element)
        
        return result
    
    def get_href(self, element):
        return (element.get_attribute("href") or '').strip()
    
    def get_value(self, element):
        return self.normalise_text(element.get_attribute("value"))
    
    def normalise_text(self, value):
        with_removed_tags = re.sub(RE_REMOVE_HTML_TAGS, '', (value or ''))
        return ' '.join(with_removed_tags.split()).strip()

    def get_innerHtml(self, element):
        return self.normalise_text(self.driver.execute_script("return arguments[0].innerHTML", element))
    
    def email_screenshot(self, email_address):
        msg = MIMEMultipart()
        msg['Subject'] = 'Your Requested Screenshot from Selenium'
        msg['To'] = email_address
        msg['From'] = email_address

        url = self.driver.current_url

        msg.attach(MIMEText(f'Here is the screenshot that you requested of page {url}'))

        part = MIMEBase('image', 'png')
        part.set_payload(self.driver.get_screenshot_as_png())
        encode_base64(part)

        part.add_header(
            'Content-Disposition',
            'attachment; filename="screenshot.png"',
        )

        msg.attach(part)

        s = smtplib.SMTP('smtp.xuhl-tr.nhs.uk')
        s.send_message(msg)
        s.quit()


class SeleniumGridHelper(SeleniumHelper):
    def __init__(self, download_directory, selenium_host, selenium_port, implicit_wait_time, browser=DesiredCapabilities.CHROME, **kwargs):

        browser['acceptInsecureCerts'] = True
        browser['acceptSslCerts'] = True


        driver = webdriver.Remote(
            command_executor=f'http://{selenium_host}:{selenium_port}/wd/hub',
            desired_capabilities=browser
        )

        super().__init__(
            driver=driver,
            download_directory=download_directory,
            **kwargs,
        )

    def close(self):
        self.driver.quit()


class SeleniumLocalHelper(SeleniumHelper):
    def __init__(self, download_directory, implicit_wait_time, headless=True, **kwargs):

        profile = webdriver.FirefoxProfile()
        profile.set_preference("browser.download.folderList", 2)
        profile.set_preference("browser.download.manager.showWhenStarting", False)
        profile.set_preference("browser.download.dir", download_directory)
        profile.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/zip")

        options = FirefoxOptions()
        if headless:
            options.add_argument("--headless")

        driver = webdriver.Firefox(options=options, firefox_profile=profile)
        driver.implicitly_wait(implicit_wait_time)

        super().__init__(
            driver=driver,
            download_directory=download_directory,
            **kwargs,
        )

    def close(self):
        self.driver.close()
