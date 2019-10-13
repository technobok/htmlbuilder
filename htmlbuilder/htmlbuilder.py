# html5 says these elements should not have a closing tags (or empty tag)
EMPTY_ELEMENTS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                 'link', 'meta', 'param', 'source', 'track', 'wbr'}

class Element:
    '''
    An HTML element. Has a tag, optionally attributes and optionally child tags
    '''
    def __init__(self, tagname, attrs=None, content=None):
        '''
        tagname = type of this tag
        attrs = list of other attribute tuples
        content = string that will be added as a TextNode (for one line
            Element creation)
        '''
        self.tagname = tagname
        self.attr = attrs if attrs is not None else []
        self.children = []
        if content is not None:
            self.append(TextNode(content))

    def append(self, child):
        '''
        child = childnode to add to this node

        returns child for storing children that are created directly in the
            arguments
        '''
        if self.tagname.lower() in EMPTY_ELEMENTS:
            raise Exception('Content not permitted on Empty elements')
        self.children.append(child)
        return child

    def render(self, depth=0, sep='  '):
        '''
        depth = depth for indentation (starting at 0 for no indentation
        sep = separator for indention, will be multiplied by the depth
        '''
        dest = []
        indent = sep * depth
        tag = self.tagname
        attrs = []
        for a in self.attr:
            attrs.append(f'{a[0]}="{a[1]}"')
        attrstr = ' '.join(attrs)
        if attrstr:
            attrstr = ' ' + attrstr

        if not self.children:
            if self.tagname.lower() in EMPTY_ELEMENTS:
                closing = '>'
            else:
                closing = ' />'
            dest.append(f'{indent}<{tag}{attrstr}{closing}')
        elif (len(self.children) == 1 and
              isinstance(self.children[0], TextNode)):
            # only 1 text node child, do it all inline
            contents = self.children[0].contents
            dest.append(f'{indent}<{tag}{attrstr}>{contents}</{tag}>')
        else:
            # has children
            dest.append(f'{indent}<{tag}{attrstr}>')
            for c in self.children:
                dest.extend(c.render(depth + 1, sep))

            dest.append(f'{indent}</{tag}>')

        return dest

class TextNode:
    def __init__(self, contents):
        '''
        contents = exact contents of the body of this element

        Can also be used for full html elements, but wont be able to search in
        them etc.
        '''
        self.contents = contents

    def render(self, depth=0, sep='  '):
        return [(sep * depth) + self.contents]

class Page:
    def __init__(self, title='', faviconpath=''):
        '''
        '''
        c = []
        self.children = c
        c.append(TextNode("<!DOCTYPE html>"))
        html = Element("html", [('lang', 'en')])
        c.append(html)
        head = html.append(Element("head"))
        head.append(Element('meta', [('charset', 'utf-8')]))
        head.append(Element('meta', [('google', 'notranslate')]))
        head.append(Element('meta', [('http-equiv', 'Content-Language'),
                                     ('content', 'en_US')]))
        head.append(Element('meta', [('http-equiv', 'X-UA-Compatible'),
                                     ('content', 'IE=edge')]))
        head.append(Element('meta', [('name', 'viewport'),
                                     ('content',
                                      'width-device-width, initial-scale=1')]))
        title = head.append(Element('title', content=title))
        if faviconpath:
            head.append(Element('link', [('rel', 'icon'),
                                         ('href', faviconpath),
                                         ('type', 'image/x-icon')]))
            head.append(Element('link', [('rel', 'shortcut icon'),
                                         ('href', faviconpath),
                                         ('type', 'image/x-icon')]))
        body = html.append(Element("body"))

        self.head = head
        self.body = body

    def __str__(self):
        dest = []
        for c in self.children:
            dest.extend(c.render())
        return '\n'.join(dest)



