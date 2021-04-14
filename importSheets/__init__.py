# import the main window object (mw) from aqt
from aqt import mw
import re
import requests
# import the "show info" tool from utils.py
from aqt.utils import showInfo, qconnect
# import all of the Qt GUI library
from aqt.qt import *
from bs4 import BeautifulSoup
# We're going to add a menu item below. First we want to create a function to
# be called when the menu item is activated.

def testFunction() -> None:
    # get the number of cards in the current collection, which is stored in
    # the main window
    sheetsurl, ok = QInputDialog.getText(mw, 'input dialog', 'Is this ok?')
    if ok:
        # https://docs.google.com/spreadsheets/d/1t2bMQamnldHL_atv0RlNlKasKs5EV1OnI_rLj8DwOCU/export?format=csv&gid=1216286449
        sheetid = str(re.findall('\/d\/(.*?)\/', sheetsurl)[0])
        csvurl = "https://docs.google.com/spreadsheets/d/"+sheetid+"/export?format=csv"
        data = download(csvurl)

        data = str(data)
        # printdata = data[0:10]
        showInfo("%s" % data)

    cardCount = mw.col.cardCount()
    # show a message box
    showInfo("Card count: %d" % cardCount)

def _parseHtmlPageToAnkiDeck(data, lazyLoadImages=False):

    orgData = _generateOrgListFromHtmlPage(data)

    return orgData

def download(url):

    response = requests.get(url)
    if response.status_code == 200:
        data = response.content
    else:
        raise Exception("Failed to get url: {}".format(response.status_code))

    data = data.decode("utf-8")

    return data


def _getCssStyles(cssData):

    # Google docs used the following class for lists $c1
    cSectionRegexPattern = "\.c\d{1,2}\{[^\}]+}"
    cssSections = re.findall(cSectionRegexPattern, cssData.text)

    cssStyles = {}
    # for each c section extract critical data
    regexValuePattern = ":[^;^}\s]+[;}]"
    startSectionRegex = "[;{]"
    for section in cssSections:
        name = re.findall("c[\d]+", section)[0]
        color = re.findall("{}{}{}".format(startSectionRegex, "color", regexValuePattern), section)
        fontStyle = re.findall("{}{}{}".format(startSectionRegex, "font-style", regexValuePattern), section)
        fontWeight = re.findall("{}{}{}".format(startSectionRegex, "font-weight", regexValuePattern), section)
        textDecoration = re.findall("{}{}{}".format(startSectionRegex, "text-decoration", regexValuePattern), section)
        verticalAlign = re.findall("{}{}{}".format(startSectionRegex, "vertical-align", regexValuePattern), section)

        # Ignore default values
        if (len(color) >0 and "color:#000000" in color[0]):
            color = []
        if (len(fontWeight) >0 and "font-weight:400" in fontWeight[0]):
            fontWeight = []
        if (len(fontStyle) >0 and "font-style:normal" in fontStyle[0]):
            fontStyle = []
        if (len(textDecoration) >0 and "text-decoration:none" in textDecoration[0]):
            textDecoration = []
        if (len(verticalAlign) >0 and "vertical-align:baseline" in verticalAlign[0]):
            verticalAlign = []

        d = [color, fontStyle, fontWeight, textDecoration, verticalAlign]

        styleValues = []
        for i in d:
            if len(i) > 0:
                cleanedStyle = i[0][1:-1]
                styleValues.append(cleanedStyle)
        cssStyles[name] = styleValues

    return cssStyles
def _startOfMultiLineComment(item):

    # Get span text
    if item.name == "p":
        line = ""
        sections = item.find_all("span")
        for span in sections:
            line += span.text
        if ("#multilinecommentstart" == line.replace(" ", "").lower()):
            return True
    return False

def _endOfMultiLineComment(item):

    # Get span text
    if item.name == "p":
        line = ""
        sections = item.find_all("span")
        for span in sections:
            line += span.text
        if ("#multilinecommentend" == line.replace(" ", "").lower()):
            return True
    return False

def _extractSpanWithStyles(soupSpan, cssStyles):

    text = soupSpan.text
    classes = soupSpan.attrs.get("class")

    if classes == None:
        return text

    relevantStyles = []
    for clazz in classes:
        if cssStyles.get(clazz) != None:
            for style in cssStyles.get(clazz):
                relevantStyles.append(style)


    if len(relevantStyles) > 0:
        styleAttributes = ""
        for i in relevantStyles:
            styleAttributes += i + ";"
        # Added whitespace around the text. The whitespace is getting stripped somewhere
        text = text.strip()
        styledText = '<span style="{}"> {} </span>'.format(styleAttributes, text)
        return styledText
    else:
        return text
def _generateOrgListFromHtmlPage(data):
    orgStar = "*"
    soup = BeautifulSoup(data, 'html.parser')
    title = soup.find("div", {"id": "title"})
    deckName = title.text
    contents = soup.find_all(["ul", "p"])

    ## Try and get CSS

    cssData = soup.find_all("style")
    cssStyles = {}
    for css in cssData:
        cssData = soup.find_all("style")[1]
        styleSection = _getCssStyles(cssData)
        cssStyles.update(styleSection)

    multiCommentSection = False
    orgFormattedFile = []
    for item in contents:
        # Handle multiLine comment section
        if _startOfMultiLineComment(item):
            multiCommentSection = True
            continue
        elif multiCommentSection and _endOfMultiLineComment(item):
            multiCommentSection = False
            continue
        elif multiCommentSection:
            continue

        # Handle normal line
        if item.name == "p":
            # Get span text
            line = ""
            textSpans = item.find_all("span")
            # print(textSpans)
            for span in textSpans:
                line += span.text

            # Get link text
            linkText = ""
            allLinks = item.find_all("a")
            for link in allLinks:
                text = link.contents
                for t in text:
                    linkText += t

            # Ignore line if span and link text are the same
            if len(line) > 0 and linkText != line:
                orgFormattedFile.append(line)

        # Hanlde list line
        elif item.name == "ul":
            # print("ul")
            listItems = item.find_all("li")

            # Item class is in the format of "lst-kix_f64mhuyvzb86-1" with last numbers as the level
            classes = item["class"]  # .split("-")[-1])
            regexSearch = "^[\w]{3}-[\w]{3,}-[\d]{1,}"
            indentation = -1
            for i in classes:
                if re.match(regexSearch, i) != None:
                    indentation = int(i.split("-")[-1])

            if (indentation == -1):
                raise Exception("Could not find the correct indentation")

            itemText = []
            imageConfig = ""
            for i in listItems:
                # Get all spans
                textSpans = i.find_all("span")
                lineOfText = ""
                for span in textSpans:
                    lineOfText += _extractSpanWithStyles(span, cssStyles)

                    # Check for images and take first
                    images = span.find_all("img")
                    if len(images) >= 1:
                        imageTemplate = " [image={}]"  # height={}, width={}
                        # Get image styles
                        styles = images[0]["style"]
                        searchRegex = "{}:\s[^;]*;"
                        height = re.findall(searchRegex.format("height"), styles)[0].split(":")[1].replace(";",
                                                                                                           "").strip()
                        width = re.findall(searchRegex.format("width"), styles)[0].split(":")[1].replace(";",
                                                                                                         "").strip()
                        imageConfig = " # height={}, width={}".format(height, width)

                        # Build image line
                        imageText = imageTemplate.format(images[0]["src"])
                        lineOfText += imageText

                # Add image metadata at end of line once
                if len(imageConfig) > 0:
                    lineOfText += imageConfig
                    imageConfig = ""

                itemText.append(lineOfText)

            indentation += 1
            orgStars = (orgStar * indentation)
            for line in itemText:
                if (_closeLineBreak(line)):
                    orgFormattedFile.append(line)
                else:
                    formattedListItem = "{} {}".format(orgStars, line)
                    orgFormattedFile.append(formattedListItem)



        else:
            pass
            # print("Unknown line type: {}".format(item.name))

    return {"deckName": deckName, "data": orgFormattedFile}
# create a new menu item, "test"
action = QAction("testing", mw)
# set it to call testFunction when it's clicked
qconnect(action.triggered, testFunction)
# and add it to the tools menu
mw.form.menuTools.addAction(action)