from collections import OrderedDict
import os
import zipfile
import re
import smtplib
import typing
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
from dataclasses import dataclass


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
        if not element:
            return None

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
        base_url=os.environ.get("BASE_URL", ""),
        implicit_wait_time=float(os.environ.get("IMPLICIT_WAIT_TIME", 1)),
        click_wait_time=float(os.environ.get("CLICK_WAIT_TIME", 1)),
        download_wait_time=float(os.environ.get("DOWNLOAD_WAIT_TIME", 60)),
        page_wait_time=float(os.environ.get("PAGE_WAIT_TIME", 5)),
        email_address=os.environ["EMAIL_ADDRESS"],
        compare_version=os.environ.get("COMPARE_VERSION", "0.0"),
        version=os.environ.get("VERSION", "0.0"),
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


class Translator:
    def __init__(self) -> None:
        self.translations: dict = {}
    
    def add_translations(self, version: str, translations: dict):

        self.translations |= translations

    def add_translation(self, version: str, from_value: str, to_value: str):
        self.translations[from_value] = to_value


class VersionTranslator:
    def __init__(self) -> None:
        self.columns: dict = {}
        self.label_translations: dict = {}
        self.value_translations: dict = {}

    def set_columns_for_version(self, ver: str, column_names: set):
        cv = version.parse(ver)
        self.columns[cv] = column_names

    def add_column(self, ver: str, column_name: str):
        cv = version.parse(ver)
        self.columns[cv].append(column_name)

    def set_label_translators_for_version(self, ver: str, translations: dict):
        cv = version.parse(ver)
        self.label_translations[cv] = translations
    
    def add_label_translator(self, ver: str, from_value: str, to_value: str):
        cv = version.parse(ver)
        self.label_translations[cv][from_value] = to_value
    
    def set_value_translators_for_version(self, ver: str, translations: dict):
        cv = version.parse(ver)
        self.value_translations[cv] = translations
    
    def add_value_translator(self, ver: str, from_value: str, to_value: str):
        cv = version.parse(ver)
        self.value_translations[cv][from_value] = to_value
    
    def translate_dictionary(self, ver: str, input: dict):
        ct: list = self._get_version(ver, self.columns)
        lt: dict = self._get_version(ver, self.value_translations)
        vt: dict = self._get_version(ver, self.value_translations)

        result = OrderedDict()

        for k, v in input.items():
            if lt and k in lt.keys():
                k = lt[k]

            if ct and k not in ct:
                continue

            if isinstance(v, typing.Hashable) and vt and v in vt.keys():
                v = lt[v]
            
            result[k] = v
        
        result = OrderedDict({key: value for key, value in sorted(result.items())})

        return result

    def cleanse_headers(self, ver: str, headers: list):
        ct: list = self._get_version(ver, self.columns)

        if not ct:
            return headers

        result = []

        for h in headers:
            if h in ct:
                result.append(h)
       
        return result

    def _get_version(self, ver: str, versions: dict):
        cv = version.parse(ver)
        pre_versions = [k for k in versions.keys() if k <= cv]

        if not pre_versions:
            return None
        
        latest_version = max(pre_versions)
        return versions[latest_version]

@dataclass(frozen=True, eq=True)
class Link:
    href: str
    name: str

class Scrubber:
    def __init__(self, helper: SeleniumHelper, version_comparator: VersionTranslator=None) -> None:
        self.helper = helper
        self.version_comparator = version_comparator or VersionTranslator()

    def get_details(self):
        parents = self.helper.get_elements(self.parent_selector)

        if len(parents) > 0:
            return self._scrape_details(parents[0])
        else:
            return None
    
    def _scrape_details(self, parent):
        return []
    
    def get_value(self, parent, header=''):
        elements = sorted(self.helper.get_elements(self.value_selector, element=parent), key=lambda x: x.tag_name)
        parents = self.get_parent_elements(elements, header)

        if len(parents) > 0:
            values_values = list(set(filter(None, [self.get_element_contents(v) for v in parents])))
            return '; '.join(str(vv) for vv in values_values)
        else:
            return self.get_element_contents(parent)
    
    def cleanse(self, value):
        if value:
            return value.replace('&nbsp;', ' ').strip()

    def get_element_contents(self, element):
        if element.tag_name == 'a':
            href = self.helper.get_href(element)
            name = self.helper.get_text(element)

            if not href and not name:
                return None

            return Link(href=self.cleanse(href), name=self.cleanse(name))
        else:
            return self.cleanse(self.helper.get_text(element))

    def get_parent_elements(self, elements, header):
        results = []

        if header == 'Description':
            for e in elements:
                print('-'*10)
                print(e.get_attribute('outerHTML'))

        for e in elements:
            ancestors = self.helper.get_elements(XpathSelector('.//ancestor-or-self::*'), element=e)
            ancestors.remove(e)
            intersection = list(set(ancestors) & set(elements))

            if len(intersection) == 0:
                results.append(e)
                break

        print(len(results))
        return results

class KeyValuePairScrubber(Scrubber):
    def __init__(self, 
                 helper: SeleniumHelper,
                 parent_selector: Selector=None,
                 pair_selector: Selector=None,
                 key_selector: Selector=None,
                 value_selector: Selector=None,
                 version_comparator: VersionTranslator=None) -> None:
        super().__init__(helper, version_comparator)
        
        self.parent_selector = parent_selector or CssSelector('ul')
        self.pair_selector = pair_selector or CssSelector('li')
        self.key_selector = key_selector or CssSelector('strong')
        self.value_selector = value_selector or CssSelector('span, a')

    def _scrape_details(self, parent):
        details = {}

        for kvpair in self.helper.get_elements(self.pair_selector, element=parent):
            title = self.helper.get_element(self.key_selector, element=kvpair, allow_null=True)
            header = self.cleanse(self.helper.get_text(title))

            if header:
                details[header] = self.get_value(kvpair)

        return self.version_comparator.translate_dictionary(self.helper.compare_version, details)


class ListScrubber(Scrubber):
    def __init__(self, 
                 helper: SeleniumHelper,
                 parent_selector: Selector=None,
                 value_selector: Selector=None,
                 version_comparator: VersionTranslator=None) -> None:
        super().__init__(helper, version_comparator)
        
        self.parent_selector = parent_selector or CssSelector('ul')
        self.value_selector = value_selector or CssSelector('li')

    def _scrape_details(self, parent):
        details = []

        for value in self.helper.get_elements(self.value_selector, element=parent):
            details.append(self.get_value(value))

        return sorted(details)


class TableScrubber(Scrubber):
    def __init__(self, 
                 helper: SeleniumHelper,
                 parent_selector: Selector=None,
                 header_selector: Selector=None,
                 row_selector: Selector=None,
                 cell_selector: Selector=None,
                 value_selector: Selector=None,
                 version_comparator: VersionTranslator=None) -> None:
        super().__init__(helper, version_comparator)
        
        self.parent_selector = parent_selector or CssSelector('table')
        self.header_selector = header_selector or CssSelector('thead tr th')
        self.row_selector = row_selector or CssSelector('tbody tr')
        self.cell_selector = cell_selector or CssSelector('td')
        self.value_selector = value_selector or CssSelector('span, a')

    def _scrape_details(self, parent):
        result = []

        headers = [self.helper.get_text(h) for h in self.helper.get_elements(self.header_selector, element=parent)]
        headers = self.version_comparator.cleanse_headers(self.helper.compare_version, headers)

        for row in self.helper.get_elements(self.row_selector, element=parent):
            details = {}

            for i, cell in enumerate(self.helper.get_elements(self.cell_selector, element=row)):
                if i < len(headers):
                    header = self.cleanse(headers[i])
                else:
                    header = str(i)

                if header:
                    details[header] = self.get_value(cell, header=header)

            result.append(self.version_comparator.translate_dictionary(self.helper.compare_version, details))

        return sorted(result, key=lambda d: str(d[[h for h in filter(None, headers)][0]]))
