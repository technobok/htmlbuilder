"""
htmlbuilder

TODO:
    - escape attributes and content
    - add 'safe' content method when escaping is not needed

Does not enforce correct html structure.
Does not prevent self referential structures (be careful with creation, 
circular structures may cause infinite loops during building or 
rendering)
"""
from __future__ import annotations
from typing import Optional, List, Tuple, Iterable
from html.parser import HTMLParser

# in html5 these elements can not have a closing tags (or empty tag)
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def makedocument(title: Optional[str] = None) -> Element:
    """
    makedocument - create a basic html document
    """
    document = Element("", idcache=True)  # container to hold the document
    document.doctype()
    html = document.html()
    head = html.head()
    if title:
        head.title(title)
    html.body()
    return document


def makeroot(tagName: str) -> Element:
    """
    makerootelement - create a root Element. Usually a html Page but could
        be a fragment (eg for HTMX)
    tagName: tag name for root element ("" for a Page)
    """
    return Element(tagName, idcache=True)  # root elements have a cache


class Element:
    """
    An HTML element. Has a tag, optionally attributes, optionally children
    """

    def __init__(
        self,
        tagName: str,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
        content: Optional[str] = None,
        parent: Optional[Element] = None,
        idcache: bool = False,
        isvoid: bool = False,
    ):
        """
        tagName: type of this tag. If tagName is empty, opening/closing tags
            are not emitted
        id: id for the tag (optional)
        classname: class(es) for this element
        attributes: an iterable of (name, value) pairs to be created as
            attributes. If source is a dict, pass d.items()
        content: string that will be output as first child, for simple
            Elements (text/comment etc)
        parent: parent element of this Element
        idcache: if true (and if parent is None), create a cache for child
            id's so that getElementById is more efficient (only at the
            root). id uniqueness is not checked if the root does not have
            an idcache.
        isvoid: set this as a void element when true. Void elements will not
            have a closing tag and cannot have children. It will be rendered
            with a self closing tag. If false, this may still be a void
            element if the tag is one of the void element tags.
        """
        self.tagName = tagName.lower()
        self.content = content
        self.parent: Optional[Element] = parent
        # holds the element with the idcache, if any.
        self.root: Optional[Element] = None
        self.idcache: Optional[dict[str, Element]] = None
        if idcache:
            self.idcache = {}
            self.root = self
        self.isvoid = isvoid or (self.tagName in VOID_ELEMENTS)

        self.attributes: Optional[dict[str, str]] = None
        self.children: Optional[list[Element]] = None

        if attributes:
            for name, value in attributes:
                self.setAttribute(name, value)
        # this will register the id
        # no need to explicity register if parent is provided
        if id:
            self.setAttribute("id", id)
        if classname:
            self.setAttribute("class", classname)

        if parent:
            parent.appendChild(self)  # will recursively register children

    def setAttribute(self, name: str, value: str) -> None:
        """
        setAttribute - set (create or overwrite) an attribute of this Element
        name: name of attribute
        value: value of attribute
        """
        if self.attributes is None:
            self.attributes = {}
        if name == "id":
            if "id" in self.attributes:
                # already have an id, remove existing
                self._removeid(value)
            self._setid(name, self)
        self.attributes[name] = value

    def removeAttribute(self, name: str) -> None:
        """
        removeAttribute - remove an attribute from this Element if it exists
        name: name of attribute to delete
        """
        if self.attributes:
            value = self.attributes.pop(name, None)
            if value and name == "id":
                self._removeid(value)

    def getAttribute(self, name: str) -> Optional[str]:
        """
        getAttribute - return the value of an attribute if it exists
        """
        if self.attributes:
            return self.attributes.get(name, None)
        return None

    @property
    def id(self) -> Optional[str]:
        """
        id - return the id of this element or None if no id
        """
        return self.getAttribute("id")

    @id.setter
    def id(self, id: str) -> None:
        """
        id - set id
        """
        self.setAttribute("id", id)

    def appendChild(self, child: Element) -> Element:
        """
        child = childnode to add to this node. Will take ownership of the
            child (ie. will remove idcache if present and set the root)

        returns child (for storing children that are created directly in the
            arguments)
        """
        if self.children is None:
            if self.isvoid:
                raise ValueError(
                    f"Content not permitted on Void elements. Tag: {self.tagName}"
                )
            self.children = []
        self.children.append(child)
        self._registerchild(child)
        return child

    def removeChild(self, child: Element) -> Element:
        """
        removeChild - remove the supplied child element from this element's
        list of children.
        child: element to remove, must be a child of this element or
            ValueError will be thrown
        """
        if self.children:
            # raises ValueError if not found
            idx = self.children.index(child)
            self._deregisterchild(child)  # recursively deregister this tree
            self.children.pop(idx)  # remove child
            child.parent = None  # clear its parent
            return child

        raise ValueError("child does not exist in this parent Element")

    @property
    def innerHTML(self) -> str:
        """
        innerHTML (getter) - return the children elements as HTML
        """
        ret: List[str] = []
        if self.children:
            for c in self.children:
                ret.extend(c.renderlist())
        return "".join(ret)

    @innerHTML.setter
    def innerHTML(self, html: str) -> None:
        """
        innerHTML (setter) - remove current children of this element, parse
        the supplied html and insert it as children to this element
        May return ValueError if this is a void element (cannot have children)
        or html is invalid.
        """
        if self.isvoid:
            raise ValueError(f"Element is a void element. Tag: {self.tagName}")
        if self.children:
            for c in self.children:
                self.removeChild(c)
        ps = parser(parent=self)
        ps.feed(html)  # this is all, the elements will be added as children to self

    def remove(self) -> None:
        """
        remove - remove this element from its parent and unregister all
        elements in this tree. Must have a parent
        """
        if self.parent:
            self.parent.removeChild(self)

    def _setid(self, id: str, element: Element) -> None:
        """
        _setid - register an id element of a child of this tree. This
        maintains an index that is used to implement a more efficient
        version of getelementbyid

        id: id name of the element being registered
        element: child element with this id
        """
        if self.idcache is not None:
            # we are the root, update idcache here
            if id in self.idcache:
                raise ValueError(f"Duplicate id: {id}")
            self.idcache[id] = element

        elif self.root:
            # there is a root higher up the tree
            self.root._setid(id, element)

        # else do nothing. No idcache and no guarantee that child id's are
        #  unique (until added to a root page)

    def _removeid(self, id: str) -> None:
        """
        _removeid - remove an id from the page

        id: id name of the element being deregistered
        """
        if self.idcache is not None:
            # we are the root, update idcache here
            self.idcache.pop(id, None)

        elif self.root:
            # there is a root higher up the tree
            self.root._removeid(id)

        # else, nothing to do

    def _registerchild(self, child: Element) -> None:
        """
        _registerchild - recursively register a child and its children
            Record the id's of all elements in the tree and set their
            root (to our root) and remove their idcache, if any

        child = childnode to add to this node
        """
        child.root = self.root
        child.idcache = None

        id = child.getAttribute("id")
        if id:
            self._setid(id, child)

        # recursively add grandchildren
        if child.children:
            for c in child.children:
                self._registerchild(c)

    def _deregisterchild(self, child: Element) -> None:
        """
        _deregisterchild - recursively deregister a child and its children.
        Remove id's from cache and clear the root

        child = childnode to deregister
        """
        id = child.getAttribute("id")
        if id:
            self._removeid(id)

        self.root = None

        # recursively remove grandchildren
        if child.children:
            for c in child.children:
                self._deregisterchild(c)

    def getElementById(self, id: str) -> Optional[Element]:
        """
        getElementById - return the Element from the tree (ie in this element
            or its children) with the supplied id. Will use a idcache if
            available

        id: id to find

        Returns first element found with the matching id
        """
        if self.idcache is not None:
            return self.idcache.get(id, None)

        # find recursively (slower way)
        if self.id == id:
            return self

        if self.children:
            for c in self.children:
                e = c.getElementById(id)
                if e:
                    return e
        return None

    def getElementsByTagName(self, tagName: str) -> List[Element]:
        """
        getElementsByTagName - return a list of elements from this (sub)tree
            with the supplied tagName. Exhaustive search, depth first

        tagName: tag name to search for. Must be lowercase as all tags are
            maintained as lowercase in tree
        """
        result: List[Element] = []

        if self.tagName == tagName:
            result.append(self)

        if self.children:
            for c in self.children:
                result.extend(c.getElementsByTagName(tagName))

        return result

    def getElementByTagName(self, tagName: str) -> Optional[Element]:
        """
        getElementByTagName - return an element from this (sub)tree
            with the supplied tagName. Returns first match immediately,
            depth first

        tagName: tag name to search for. Must be lowercase as all tags are
            maintained as lowercase in tree

        Returns the first matching element of this tag type
        """
        if self.tagName == tagName:
            return self

        if self.children:
            for c in self.children:
                e = c.getElementByTagName(tagName)
                if e:
                    return e

        return None

    def renderlist(self) -> list[str]:
        """
        renderlist - render this element and recursively, all child elements

        returns a list of strings that can be joined to create the rendered html
        (or can be appended to parent's html list)
        """
        dest: list[str] = []
        if self.tagName:
            dest.append("<" + self.tagName)

            if self.attributes:
                for k, v in self.attributes.items():
                    dest.append(f' {k}="{v}"')

            if self.isvoid:
                dest.append(" />")
                return dest

            dest.append(">")

        if self.content:
            dest.append(self.content)

        if self.children:
            for c in self.children:
                dest.extend(c.renderlist())

        if self.tagName:
            dest.append(f"</{self.tagName}>")

        return dest

    def render(self) -> str:
        """
        render - render this page to a string of html
        """
        dest = self.renderlist()
        return "".join(dest)

    def __str__(self) -> str:
        """
        __str__
        """
        return self.render()

    def doctype(self, text: str = "<!DOCTYPE html>") -> Element:
        """
        doctype - add doctype element (an unescaped text string)

        text: the full text of the doctype, defaults to the standard
            short docstring
        """
        return Element("", content=text, parent=self, isvoid=True)

    def text(self, text: str) -> Element:
        """
        text - create a text node and add it as a child of this element

        text: raw string to include
        (A text node is simply a node with content but no tag or attributes or
         children)

        TODO: escape the text
        """
        return Element("", content=text, parent=self, isvoid=True)

    def comment(self, comment: str) -> Element:
        """
        comment - add a comment and add it as a child of this element

        comment - comment string (without delimiters). Not parsed or escaped
        TODO: escape the comment
        """
        text = "<!-- " + comment + " -->"
        return Element("", content=text, parent=self, isvoid=True)

    # helper methods to create html elements
    # see https://developer.mozilla.org/en-US/docs/Web/HTML/Element

    # main root element

    def html(self) -> Element:
        """
        html - add a html (root) element as a child of this element.
            The root element of this document.
        """
        return Element("html", parent=self)

    # document metadata elements

    def base(self, href: Optional[str] = None, target: Optional[str] = None) -> Element:
        """
        base - add a base element as a child of this element.
            Specifies the base URL for all relative URLs in this document.
        """
        attribs = []
        if href:
            attribs.append(("href", href))
        if target:
            attribs.append(("target", target))
        return Element("base", attributes=attribs, parent=self)

    def head(self) -> Element:
        """
        head - add a head element as a child of this element.
            Contains metadata about this document.
        """
        return Element("head", parent=self)

    def link(self, href: Optional[str] = None, rel: Optional[str] = None) -> Element:
        """
        link - add a link element as a child of this element.
            Specifies links to external resources (eg CSS, favicon).
        """
        attribs = []
        if href:
            attribs.append(("href", href))
        if rel:
            attribs.append(("rel", rel))
        return Element("link", attributes=attribs, parent=self)

    def meta(
        self, name: Optional[str] = None, content: Optional[str] = None
    ) -> Element:
        """
        meta - add a meta element as a child of this element.
            Specifies misc. additional metadata for this document.
        """
        attribs = []
        if name:
            attribs.append(("name", name))
        if content:
            attribs.append(("content", content))
        return Element("meta", attributes=attribs, parent=self)

    def style(self) -> Element:
        """
        style - add a style element as a child of this element.
            Contains inline style information for this document.
        """
        return Element("style", parent=self)

    def title(self, title: str) -> Element:
        """
        title - add a title element as a child of this element.
            Specifies this document's title.
        """
        e = Element("title", parent=self)
        e.text(title)
        return e

    # sectioning root elements

    def body(self, attributes: Optional[Iterable[Tuple[str, str]]] = None) -> Element:
        """
        body - add a body element as a child of this element.
            Contains the content of the html document.
        """
        return Element("body", attributes=attributes, parent=self)

    # content sectioning elements

    def address(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        address - add a address element as a child of this element
            Contains contact information for person/organisation
        """
        return Element(
            "address", id=id, classname=classname, attributes=attributes, parent=self
        )

    def article(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        article - add a article element as a child of this element.
            Represents a self-contained composition in a document.
        """
        return Element(
            "article", id=id, classname=classname, attributes=attributes, parent=self
        )

    def aside(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        aside - add a aside element as a child of this element.
            Represents indirectly related content.
        """
        return Element(
            "aside", id=id, classname=classname, attributes=attributes, parent=self
        )

    def footer(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        footer - add a footer element as a child of this element.
            Represents a footer for the nearest ancestor section.
        """
        return Element(
            "footer", id=id, classname=classname, attributes=attributes, parent=self
        )

    def header(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        header - add a header element as a child of this element.
            Represents introductory content.
        """
        return Element(
            "header", id=id, classname=classname, attributes=attributes, parent=self
        )

    def h1(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        h1 - add a h1 element as a child of this element
            Represents a level 1 section heading.
        """
        return Element(
            "h1", id=id, classname=classname, attributes=attributes, parent=self
        )

    def h2(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        h2 - add a h2 element as a child of this element
            Represents a level 2 section heading.
        """
        return Element(
            "h2", id=id, classname=classname, attributes=attributes, parent=self
        )

    def h3(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        h3 - add a h3 element as a child of this element
            Represents a level 3 section heading.
        """
        return Element(
            "h3", id=id, classname=classname, attributes=attributes, parent=self
        )

    def h4(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        h4 - add a h4 element as a child of this element
            Represents a level 4 section heading.
        """
        return Element(
            "h4", id=id, classname=classname, attributes=attributes, parent=self
        )

    def h5(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        h5 - add a h5 element as a child of this element
            Represents a level 5 section heading.
        """
        return Element(
            "h5", id=id, classname=classname, attributes=attributes, parent=self
        )

    def h6(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        h6 - add a h6 element as a child of this element
            Represents a level 6 section heading.
        """
        return Element(
            "h6", id=id, classname=classname, attributes=attributes, parent=self
        )

    def hgroup(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        hgroup - add a hgroup element as a child of this element
            Represents a heading grouped with secondary content.
        """
        return Element(
            "hgroup", id=id, classname=classname, attributes=attributes, parent=self
        )

    def main(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        main - add a main element as a child of this element
            Represents the dominant content of the body.
        """
        return Element(
            "main", id=id, classname=classname, attributes=attributes, parent=self
        )

    def nav(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        nav - add a nav element as a child of this element
            Represents a section providing navigation links within a document.
        """
        return Element(
            "nav", id=id, classname=classname, attributes=attributes, parent=self
        )

    def section(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        section - add a section element as a child of this element
            Represents a standalone section of a document.
        """
        return Element(
            "section", id=id, classname=classname, attributes=attributes, parent=self
        )

    def search(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        search - add a search element as a child of this element
            Represents a section that contains forms controls for searching/filtering.
        """
        return Element(
            "search", id=id, classname=classname, attributes=attributes, parent=self
        )

    # text content elements

    def blockquote(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        blockquote - add a blockquote element as a child of this element
            Indicates the enclosed is an extended quatation (typically indented).
        """
        return Element(
            "blockquote", id=id, classname=classname, attributes=attributes, parent=self
        )

    def dd(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        dd - add a dd element as a child of this element
            Provides the value for the preceding <dt> (definition term).
        """
        return Element(
            "dd", id=id, classname=classname, attributes=attributes, parent=self
        )

    def div(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        div - add a div element as a child of this element
            Generic container for flow content.
        """
        return Element(
            "div", id=id, classname=classname, attributes=attributes, parent=self
        )

    def dl(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        dl - add a dl element as a child of this element
            Represents a list of definitions specified using <dt> <dd> pairs.
        """
        return Element(
            "dl", id=id, classname=classname, attributes=attributes, parent=self
        )

    def dt(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        dt - add a dt element as a child of this element
            Specifies a definition term in a definition list <dl>
        """
        return Element(
            "dt", id=id, classname=classname, attributes=attributes, parent=self
        )

    def figcaption(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        figcaption - add a figcaption element as a child of this element
            Represents a caption for the contents of a parent <figure>
        """
        return Element(
            "figcaption", id=id, classname=classname, attributes=attributes, parent=self
        )

    def figure(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        figure - add a figure element as a child of this element
            Represents a self-contained figure.
        """
        return Element(
            "figure", id=id, classname=classname, attributes=attributes, parent=self
        )

    def hr(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        hr - add a hr element as a child of this element
            Represents a break between paragraph level content.
        """
        return Element(
            "hr", id=id, classname=classname, attributes=attributes, parent=self
        )

    def li(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        li - add a li element as a child of this element
            Represents an item in a list (<ol> or <ul>)

        text: text to add inside the li
        """
        e = Element(
            "li", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def menu(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        menu - add a menu element as a child of this element
            Represents an unordered list of items similar to <ul> but intended
            for interactive items.
        """
        return Element(
            "menu", id=id, classname=classname, attributes=attributes, parent=self
        )

    def ol(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        ol - add a ol element as a child of this element
            Represents and ordered list of items.
        """
        return Element(
            "ol", id=id, classname=classname, attributes=attributes, parent=self
        )

    def p(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        p - add a p element as a child of this element
            Represents a paragraph.
        """
        e = Element("p", id=id, classname=classname, attributes=attributes, parent=self)
        if text:
            e.text(text)
        return e

    def pre(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        pre - add a pre element as a child of this element
            Represents preformatted text.
        """
        e = Element(
            "pre", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def ul(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        ul - add a ul element as a child of this element
            Represents an unordered list of items.
        """
        return Element(
            "ul", id=id, classname=classname, attributes=attributes, parent=self
        )

    # inline text elements

    def a(
        self,
        href: Optional[str] = None,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        a - add a 'a' element as a child of this element
            Represents and anchor element, a hyperlink.
        """
        attr = []
        if href:
            attr.append(("href", href))
        if attributes:
            attr.extend(attributes)
        e = Element("a", id=id, classname=classname, attributes=attr, parent=self)
        if text:
            e.text(text)
        return e

    def abbr(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        abbr - add a abbr element as a child of this element
            Represents and abbreviation.
        """
        e = Element(
            "abbr", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def b(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        b - add a b element as a child of this element
            Used to draw attention to content (previously, boldface)
        """
        e = Element("b", id=id, classname=classname, attributes=attributes, parent=self)
        if text:
            e.text(text)
        return e

    def bdi(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        bdi - add a bdi element as a child of this element
            Isolate contents from surrounds for the bidirectional algorithm
        """
        e = Element(
            "bdi", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def bdo(
        self,
        text: Optional[str] = None,
        dir: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        bdo - add a bdo element as a child of this element
            Override the bidirectionality of contained text.

        dir = 'ltr' or 'rtl'
        """
        attr = []
        if dir:
            attr.append(("dir", dir))
        if attributes:
            attr.extend(attributes)
        e = Element("bdo", id=id, classname=classname, attributes=attr, parent=self)
        if text:
            e.text(text)
        return e

    def br(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        br - add a br element as a child of this element
            A line break.
        """
        return Element(
            "br", id=id, classname=classname, attributes=attributes, parent=self
        )

    def cite(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        cite - add a cite element as a child of this element
            Mark up the title of a cited work.
        """
        return Element(
            "cite", id=id, classname=classname, attributes=attributes, parent=self
        )

    def code(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        code - add a code element as a child of this element
            Represents a fragment of computer code.
        """
        e = Element(
            "code", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def data(
        self,
        value: Optional[str] = None,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        data - add a data element as a child of this element
            Represents content that has a machine readable value. See also <time>
        """
        attr = []
        if value:
            attr.append(("value", value))
        if attributes:
            attr.extend(attributes)
        e = Element("data", id=id, classname=classname, attributes=attr, parent=self)
        if text:
            e.text(text)
        return e

    def dfn(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        dfn - add a dnf element as a child of this element
           Used to indicate the contents is a term to be defined.
        """
        e = Element(
            "dfn", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def em(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        em - add a em element as a child of this element
            Marks text to be emphasised.
        """
        e = Element(
            "em", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def i(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        i - add a i element as a child of this element
            Marks text that is set of from normal text (terms, designations).
            Previously italics.
        """
        e = Element("i", id=id, classname=classname, attributes=attributes, parent=self)
        if text:
            e.text(text)
        return e

    def kbd(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        kbd - add a kbd element as a child of this element
            Presents textual user input from a keyboard.
        """
        e = Element(
            "kbd", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def mark(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        mark - add a mark element as a child of this element
            Represents text marked or highlighted for reference or notation.
        """
        e = Element(
            "mark", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def q(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        q - add a q element as a child of this element
            Represents a short, inline quote. See also <blockquote> for longer
            quotes.
        """
        e = Element("q", id=id, classname=classname, attributes=attributes, parent=self)
        if text:
            e.text(text)
        return e

    def rp(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        rp - add a rp element as a child of this element
            Provide fallback parentheses for the <ruby> element.
        """
        e = Element(
            "rp", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def rt(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        rt - add a rt element as a child of this element
            Specifies the ruby text component of a ruby annotation.
        """
        e = Element(
            "rt", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def ruby(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        ruby - add a ruby element as a child of this element
            Presents small annotations rendered near base text usually for
            showing pronunciation of East Asian characters.
        """
        e = Element(
            "ruby", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def s(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        s - add a s element as a child of this element
            Represents strikethrough text for content that is no longer relevant.
        """
        e = Element("s", id=id, classname=classname, attributes=attributes, parent=self)
        if text:
            e.text(text)
        return e

    def samp(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        samp - add a samp element as a child of this element
            Represents sample or quoted output.
        """
        e = Element(
            "samp", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def small(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        small - add a small element as a child of this element
            Represents side-comments and small print.
        """
        e = Element(
            "small", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def span(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        span - add a span element as a child of this element
            Generic inline container for phrasing content.
        """
        e = Element(
            "span", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def strong(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        strong - add a strong element as a child of this element
            Indicates contents have strong importance.
        """
        e = Element(
            "strong", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def sub(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        sub - add a sub element as a child of this element
            Represents subscript content.
        """
        e = Element(
            "sub", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def sup(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        sup - add a sup element as a child of this element
            Represents superscript content.
        """
        e = Element(
            "sup", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def time(
        self,
        datetime: Optional[str] = None,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        time - add a time element as a child of this element
            Represents a point in time. Can have machine readable 'datetime' attr.
        """
        attr = []
        if datetime:
            attr.append(("datetime", datetime))
        if attributes:
            attr.extend(attributes)
        e = Element("time", id=id, classname=classname, attributes=attr, parent=self)
        if text:
            e.text(text)
        return e

    def u(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        u - add a u element as a child of this element
            Represents unarticulated content. Previously 'underline'
        """
        e = Element("u", id=id, classname=classname, attributes=attributes, parent=self)
        if text:
            e.text(text)
        return e

    def var(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        var - add a var element as a child of this element
            Represents the name of a variable (mathematical or programming)
        """
        e = Element(
            "var", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def wbr(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        wbr - add a wbr element as a child of this element
            Represents a word break opportunity.
        """
        e = Element(
            "wbr", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    # image and multimedia content elements

    def area(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        area - add an area element as a child of this element
            Represents an area inside an image map.
            Typically has shape, coords, href, target and/or alt attrs.
        """
        e = Element(
            "area", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    def audio(
        self,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        audio - add an audio element as a child of this element
            Represents embedded sounds contents.
        """
        attr = []
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("audio", id=id, classname=classname, attributes=attr, parent=self)
        return e

    def img(
        self,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        img - add an img element as a child of this element
            Represents an embedded image.
        """
        attr = []
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("img", id=id, classname=classname, attributes=attr, parent=self)
        return e

    def map(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        map - add a map element as a child of this element
            Represents an image map. Used with <area>
        """
        e = Element(
            "map", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    def track(
        self,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        track - add a track element as a child of this element
            Represents a track element used as a child of <audio> or <video>.
        """
        attr = []
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("track", id=id, classname=classname, attributes=attr, parent=self)
        return e

    def video(
        self,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        video - add a video element as a child of this element
            Represents embedded video.
        """
        attr = []
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("video", id=id, classname=classname, attributes=attr, parent=self)
        return e

    # embedded content elements

    def embed(
        self,
        type: Optional[str] = None,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        embed - add a embed element as a child of this element
            Represents embedded content.
        """
        attr = []
        if type:
            attr.append(("type", type))
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("embed", id=id, classname=classname, attributes=attr, parent=self)
        return e

    def iframe(
        self,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        iframe - add an iframe element as a child of this element
            Represents a nested browsing context within the current document.
        """
        attr = []
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("iframe", id=id, classname=classname, attributes=attr, parent=self)
        return e

    def object(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        object - add an object element as a child of this element
            Represents an external resource.
        """
        e = Element(
            "object", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    def picture(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        picture - add a picture element as a child of this element
            Represents a list of alternate sources for an <img> element.
        """
        e = Element(
            "picture", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    def portal(
        self,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        portal - add a portal element as a child of this element
            Represents an embedded html page. Experimental.
        """
        attr = []
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("portal", id=id, classname=classname, attributes=attr, parent=self)
        return e

    def source(
        self,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        source - add a source element as a child of this element
            Specifies one or more media resources for <picture>, <audio> and
            <video> elements.
        """
        attr = []
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("source", id=id, classname=classname, attributes=attr, parent=self)
        return e

    # SVG and MathML elements.

    def svg(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        svg - add an svg element as a child of this element
            Represents a svg (Sclable Vector Graphics) container.
        """
        e = Element(
            "svg", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    def math(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        math - add a math element as a child of this element
            Represents a MathML container.
        """
        e = Element(
            "math", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    # Scripting elements

    def canvas(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        canvas - add a canvas element as a child of this element
            Represents a Canvas in the document that can be interacted with
            via canvas scripting or WebGL API's.
        """
        e = Element(
            "canvas", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    def noscript(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        noscript - add a noscript element as a child of this element
            Represents a section that will be inserted if a script type on
            the page is unsupported or turned off.
        """
        e = Element(
            "noscript", id=id, classname=classname, attributes=attributes, parent=self
        )
        return e

    def script(
        self,
        src: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        script - add a script element as a child of this element
            Embeds executeble code or data. Typically to refer to JavaScript
            code.
        """
        attr = []
        if src:
            attr.append(("src", src))
        if attributes:
            attr.extend(attributes)
        e = Element("script", id=id, classname=classname, attributes=attr, parent=self)
        return e

    # demarcating edits elements

    def del_(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        del_ - add a del element as a child of this element
            Represents a section that has been deleted from a document.
            Note: method name differs from html element name because it is a
            python keyword.
        """
        return Element(
            "del", id=id, classname=classname, attributes=attributes, parent=self
        )

    def ins(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        ins - add a ins element as a child of this element
            Represents a section that has been inserted into a document.
        """
        return Element(
            "ins", id=id, classname=classname, attributes=attributes, parent=self
        )

    # table elements

    def caption(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        caption - add a caption element as a child of this element
            Represents a caption or title of a table.
        """
        e = Element(
            "caption", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def col(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        col - add a col element as a child of this element
            Represents one or more columns as part of a <table> <colgroup> element.
        """
        return Element(
            "col", id=id, classname=classname, attributes=attributes, parent=self
        )

    def colgroup(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        colgroup - add a colgroup element as a child of this element
            Represents a group of columns within a <table> element
        """
        return Element(
            "colgroup", id=id, classname=classname, attributes=attributes, parent=self
        )

    def table(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        table - add a table element as a child of this element
            Represents a tabular data
        """
        return Element(
            "table", id=id, classname=classname, attributes=attributes, parent=self
        )

    def tbody(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        tbody - add a tbody element as a child of this element
            Encapsulates a set of table rows (<tr>) indicating the comprise
            the body of <table> data.
        """
        return Element(
            "tbody", id=id, classname=classname, attributes=attributes, parent=self
        )

    def td(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        td - add a td element as a child of this element
            Table (<table>) cell data element. Child of <tr>.
        """
        e = Element(
            "td", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def tfoot(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        tfoot - add a tfoot element as a child of this element
            Encapsulates a set of table rows (<tr>) indicating the comprise
            the foot of <table> data.
        """
        return Element(
            "tfoot", id=id, classname=classname, attributes=attributes, parent=self
        )

    def th(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        th - add a th element as a child of this element
            Table (<table>) cell header element. Child of <tr>.
        """
        e = Element(
            "th", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def thead(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        thead - add a thead element as a child of this element
            Encapsulates a set of table rows (<tr>) indicating the comprise
            the head of <table> data.
        """
        return Element(
            "thead", id=id, classname=classname, attributes=attributes, parent=self
        )

    def tr(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        tr - add a tr element as a child of this element
            Table (<table>) row of cells. Contains <td> or <th> cells.
        """
        return Element(
            "tr", id=id, classname=classname, attributes=attributes, parent=self
        )

    # form elements

    def button(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        button - add a button element as a child of this element
            Represents a interactive element that can be activated (typically
            pressed/clicked)
        """
        e = Element(
            "button", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def datalist(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        datalist - add a datalist element as a child of this element
            A set of <option> elements representing permissible options for
            other controls.
        """
        return Element(
            "datalist", id=id, classname=classname, attributes=attributes, parent=self
        )

    def fieldset(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        fieldset - add a fieldset element as a child of this element
            Used to group several controls and labels within a web form.
        """
        return Element(
            "fieldset", id=id, classname=classname, attributes=attributes, parent=self
        )

    def form(
        self,
        action: Optional[str] = None,
        method: Optional[str] = "get",
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        form - add a form element as a child of this element
            Represents a document section containing interactive controls for
            submitting information.

        action: URL to process submitted data
        method: http method to submit data (default: "get")
        """
        attr = []
        if action:
            attr.append(("action", action))
        if method:
            attr.append(("method", method))
        if attributes:
            attr.extend(attributes)
        e = Element("form", id=id, classname=classname, attributes=attr, parent=self)
        return e

    def input(
        self,
        type: Optional[str] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        input - add an input element as a child of this element
            Represents an interactive control to be used within web <form>s

        name: name of control. Submitted with form data.
        type: control type: button, checkbox, color, date, datetime-local,
            email, file, hidden, image, month, number, password, radio,
            range, reset, search, submit, tel, text, time, url, week
        """
        attr = []
        if type:
            attr.append(("type", type))
        if name:
            attr.append(("name", name))
        if attributes:
            attr.extend(attributes)
        e = Element("input", id=id, classname=classname, attributes=attr, parent=self)
        return e

    def label(
        self,
        for_: Optional[str] = None,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        label - add an label element as a child of this element
            Represents a document section containing interactive controls for
            submitting information.

        for_: related element that this label is for. 'for' attribute
            (parameter name differs because 'for' is a python keyword)
        text:
        """
        attr = []
        if for_:
            attr.append(("for", for_))
        if attributes:
            attr.extend(attributes)
        e = Element("label", id=id, classname=classname, attributes=attr, parent=self)
        if text:
            e.text(text)
        return e

    def legend(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        legend - add an legend element as a child of this element
            Represents a caption for its parent <fieldset>
        """
        e = Element(
            "legend", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def meter(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        meter - add a meter element as a child of this element
            Represents a scalar value within a specfied range or a fractional
            value
        """
        return Element(
            "meter", id=id, classname=classname, attributes=attributes, parent=self
        )

    def optgroup(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        optgroup - add a optgroup element as a child of this element
            Creates a grouping of options within a <select> element.
        """
        return Element(
            "optgroup", id=id, classname=classname, attributes=attributes, parent=self
        )

    def option(
        self,
        value: Optional[str] = None,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        option - add an option element as a child of this element
            Represents an option within a <select>, <optgroup> or <datalist>

        value: the content of this option for form submission
        text:
        """
        attr = []
        if value:
            attr.append(("value", value))
        if attributes:
            attr.extend(attributes)
        e = Element("option", id=id, classname=classname, attributes=attr, parent=self)
        if text:
            e.text(text)
        return e

    def output(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        output - add a output element as a child of this element
            A container element into which results can be injected.
        """
        return Element(
            "output", id=id, classname=classname, attributes=attributes, parent=self
        )

    def progress(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        progress - add a progress element as a child of this element
            Represents an indicator showing completiong progress of a task.
        """
        return Element(
            "progress", id=id, classname=classname, attributes=attributes, parent=self
        )

    def select(
        self,
        name: Optional[str] = None,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        select - add an select element as a child of this element
            Represents a control that provides a menu of options. Child
            <option>s must be defined.

        name: name of control. Submitted with form data.
        """
        attr = []
        if name:
            attr.append(("name", name))
        if attributes:
            attr.extend(attributes)
        e = Element("select", id=id, classname=classname, attributes=attr, parent=self)
        if text:
            e.text(text)
        return e

    def textarea(
        self,
        name: Optional[str] = None,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        textarea - add a textarea element as a child of this element
            Represents a multi-line plain-text editing control

        name: name of control. Submitted with form data.
        """
        attr = []
        if name:
            attr.append(("name", name))
        if attributes:
            attr.extend(attributes)
        e = Element(
            "textarea", id=id, classname=classname, attributes=attr, parent=self
        )
        if text:
            e.text(text)
        return e

    # interactive elements

    def details(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        details - add a details element as a child of this element
            Represents a widget that displays additional information only when
            toggled into the "open" state.
        """
        e = Element(
            "details", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def dialog(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        dialog - add a dialog element as a child of this element
            Represents an inerative component: dialog box, dismissable alert
            etc.
        """
        return Element(
            "dialog", id=id, classname=classname, attributes=attributes, parent=self
        )

    def summary(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        summary - add a summary element as a child of this element
            Represents a summary or caption for a <details> element. Clicking
            this element, toggles the open state of the <details> parent.
        """
        e = Element(
            "summary", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    # web component elements

    def slot(
        self,
        text: Optional[str] = None,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        slot - add a slot element as a child of this element
            Represents a placeholder within a web component for placing markup.
        """
        e = Element(
            "slot", id=id, classname=classname, attributes=attributes, parent=self
        )
        if text:
            e.text(text)
        return e

    def template(
        self,
        id: Optional[str] = None,
        classname: Optional[str] = None,
        attributes: Optional[Iterable[Tuple[str, str]]] = None,
    ) -> Element:
        """
        template - add a template element as a child of this element
            Element that holds html fragments which will not be rendered but
            are available to JavaScript.
        """
        return Element(
            "template", id=id, classname=classname, attributes=attributes, parent=self
        )


class parser(HTMLParser):
    """
    parser - parse HTML text into an Element (as children)
    """

    def __init__(self, parent: Optional[Element] = None):
        super().__init__()
        self.elementstack: List[Element] = []
        if not parent:
            parent = makeroot("")
        self.elementstack.append(parent)

    # def handle_starttag(self, tag: Optional[str], attrs: Iterable[Tuple[str, str]]) -> None:
    def handle_starttag(self, tag: str, attrs: Iterable) -> None:
        e = Element(tag, attributes=attrs, parent=self.elementstack[-1])
        self.elementstack.append(e)

    def handle_endtag(self, tag: str) -> None:
        e = self.elementstack.pop()
        if e.tagName != tag:
            raise ValueError(
                f"Expected a closing {e.tagName} tag but received {tag} at {self.getpos()}"
            )

    def handle_data(self, data: str) -> None:
        self.elementstack[-1].text(data)

    def handle_comment(self, data: str) -> None:
        self.elementstack[-1].comment(f"<!-- {data} -->")

    def handle_decl(self, decl: str) -> None:
        self.elementstack[-1].comment(f"<!{decl}>")

    # use feed() to send text to parser
    # def feed(text)

    def get(self) -> Element:
        """
        get - return the top level of the created element tree after
        parsing. Throws ValueError if the tree was not in balance or no top
        level element available.
        """
        if len(self.elementstack) != 1:
            raise ValueError(
                f"Expected 1 element on stack; {len(self.elementstack)} found"
            )
        return self.elementstack[0]


if __name__ == "__main__":
    p = makedocument()

    print(p.render())
