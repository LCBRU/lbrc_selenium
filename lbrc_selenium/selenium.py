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
from selenium.common.exceptions import UnexpectedAlertPresentException
from packaging import version


RE_REMOVE_HTML_TAGS = re.compile('<.*?>')


# Selectors

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

class TagSelector(Selector):
    def __init__(self, query):
        super().__init__(query, By.TAG_NAME)

class NameSelector(Selector):
    def __init__(self, query):
        super().__init__(query, By.NAME)

class ClassSelector(Selector):
    def __init__(self, query):
        super().__init__(query, By.CLASS_NAME)

class IdSelector(Selector):
    def __init__(self, query):
        super().__init__(query, By.ID)

    


# Actions

class Action:
    def __init__(self, helper, selector):
        self.helper = helper
        self.selector = selector

    def do(self):
        retried = 0

        while True:
            try:
                self._do()

                return

            except Exception as e:
                if retried > 2:
                    raise e

                sleep(1)
                retried += 1

                print('Retrying...')

    def _do(self):
        raise NotImplementedError()


class SelectAction(Action):
    def __init__(self, helper, select_selector, item_selector):
        super().__init__(helper, select_selector)
        self.item_selector = item_selector

    def _do(self):
        self.helper.click_element(selector=self.selector)
        self.helper.click_element(selector=self.item_selector)


class TypeInTextboxAction(Action):
    def __init__(self, helper, selector, text):
        super().__init__(helper, selector)
        self.text = text

    def _do(self):
        self.helper.type_in_textbox_selector(
            selector=self.selector,
            text=self.text,
        )


class ClickAction(Action):
    def __init__(self, helper, selector):
        super().__init__(helper, selector)

    def _do(self):
        self.helper.click_element(selector=self.selector)


class EnsureAction(Action):
    def __init__(self, helper, selector):
        super().__init__(helper, selector)

    def _do(self):
        self.helper.get_element_selector(selector=self.selector)


class SeleniumHelper:
    def __init__(
        self,
        driver,
        download_directory,
        output_directory,
        base_url,
        quitter=False,
        click_wait_time=0.2,
        download_wait_time=5,
        page_wait_time=1,
        email_address=None,
        version='0.0.0',
        compare_version='0.0.0',
    ):
        self.click_wait_time = click_wait_time
        self.download_wait_time = download_wait_time
        self.page_wait_time = page_wait_time
        self.version = version

        self.driver = driver

        self.base_url = base_url
        self.quitter = quitter

        self.email_address = email_address

        self.compare_version = compare_version

        self.download_directory = Path(download_directory)
        self.download_directory.mkdir(parents=True, exist_ok=True)
        self._clear_directory(self.download_directory)

        self.output_directory = Path(output_directory) / self.version
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def unzip_download_directory_contents(self):
        for zp in self._download_directory.iterdir():
            with zipfile.ZipFile(zp, "r") as zf:
                zf.extractall(self._download_directory)
    
    def _clear_directory(self, directory):
        for f in directory.iterdir():
            f.unlink()
    
    def get_compare_version_item(self, versions):
        cv = version.parse(self.compare_version)
        latest_version = max([k for k in versions.keys() if version.parse(k) <= cv])
        return versions[latest_version]
        
    def get_version_item(self, versions):
        cv = version.parse(self.version)
        latest_version = max(map(version.parse, [k for k in versions.keys() if version.parse(k) <= cv]))
        return versions[str(latest_version)]
        
    def get(self, url):
        base = self.base_url

        self.driver.get(urljoin(base, url))

        for i in range(20):
            try:
                self.get_element(CssSelector('body'), allow_null=False)
            except UnexpectedAlertPresentException as e:
                # self.driver.switch_to.alert.accept();
                sleep(1)

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
        if element:
            return (element.get_attribute("href") or '').strip()
    
    def get_name(self, element):
        if element:
            return (element.get_attribute("name") or '').strip()
    
    def get_value(self, element):
        if element:
            return self.normalise_text(element.get_attribute("value"))
    
    def normalise_text(self, value):
        with_removed_tags = re.sub(RE_REMOVE_HTML_TAGS, '', (value or ''))
        return ' '.join(with_removed_tags.split()).strip()

    def get_innerHtml(self, element):
        return self.normalise_text(self.driver.execute_script("return arguments[0].innerHTML", element))

    def save_screenshot(self, path):    
        self.driver.save_screenshot(path)

    def email_screenshot(self):
        msg = MIMEMultipart()
        msg['Subject'] = 'Your Requested Screenshot from Selenium'
        msg['To'] = self.email_address
        msg['From'] = self.email_address

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

    def close(self):
        if self.quitter:
            self.driver.quit()
        else:
            self.driver.close()


def get_selenium(helper_class=SeleniumHelper):
    args = dict(
        download_directory=os.environ["DOWNLOAD_DIRECTORY"],
        output_directory=os.environ["OUTPUT_DIRECTORY"],
        base_url=os.environ["BASE_URL"],
        implicit_wait_time=float(os.environ["IMPLICIT_WAIT_TIME"]),
        click_wait_time=float(os.environ["CLICK_WAIT_TIME"]),
        download_wait_time=float(os.environ["DOWNLOAD_WAIT_TIME"]),
        page_wait_time=float(os.environ["PAGE_WAIT_TIME"]),
        email_address=os.environ["EMAIL_ADDRESS"],
        compare_version=os.environ["COMPARE_VERSION"],
        version=os.environ["VERSION"],
    )

    if os.environ.get("SELENIUM_HOST", None):
        return get_selenium_grid_helper(
            helper_class=helper_class,
            selenium_host=os.environ["SELENIUM_HOST"],
            selenium_port=os.environ.get("SELENIUM_PORT", '4444'),
            **args,
        )
    else:
        return get_selenium_local_helper(
            helper_class=helper_class,
            headless=os.environ.get("SELENIUM_HEADLESS", False),
            **args,
        )


def get_selenium_grid_helper(helper_class, download_directory, selenium_host, selenium_port, implicit_wait_time, browser=DesiredCapabilities.CHROME, **kwargs):
    browser['acceptInsecureCerts'] = True
    browser['acceptSslCerts'] = True

    driver = webdriver.Remote(
        command_executor=f'http://{selenium_host}:{selenium_port}/wd/hub',
        desired_capabilities=browser
    )

    return helper_class(
        driver=driver,
        download_directory=download_directory,
        quitter=True,
        **kwargs,
    )


def get_selenium_local_helper(helper_class, download_directory, implicit_wait_time, headless=True, **kwargs):
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

    return helper_class(
        driver=driver,
        download_directory=download_directory,
        **kwargs,
    )


class VersionTranslator:
    def __init__(self) -> None:
        self.columns = {}
        self.label_translations = {}
        self.value_translations = {}

    def add_column(self, version, column_name):
        self.columns[version].append(column_name)

    def add_label_translator(self, version, from_value, to_value):
        self.label_translations[version].append((from_value, to_value))
    
    def add_value_translator(self, version, from_value, to_value):
        self.value_translations[version].append((from_value, to_value))

    def translate_dictionary(self, version, input):
        return input
