import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const bridgeTemplate = readFileSync(
  new URL('../../web/web_dock_bridge.js', import.meta.url),
  'utf8',
)

class FakeTextNode {
  constructor(text) {
    this.nodeType = 3
    this.textContent = text
    this.parentNode = null
    this.parentElement = null
  }
}

class FakeElement {
  constructor(tagName = 'div') {
    this.nodeType = 1
    this.tagName = tagName.toUpperCase()
    this.childNodes = []
    this.children = []
    this.parentNode = null
    this.parentElement = null
    this.style = {}
    this.dataset = {}
    this.attributes = new Map()
    this.rect = { left: 0, top: 0, width: 100, height: 20 }
  }

  appendChild(node) {
    node.parentNode = this
    node.parentElement = this
    this.childNodes.push(node)
    if (node.nodeType === 1) {
      this.children.push(node)
    }
    return node
  }

  append(node) {
    return this.appendChild(node)
  }

  remove() {
    if (!this.parentNode) return
    this.parentNode.childNodes = this.parentNode.childNodes.filter(
      (node) => node !== this,
    )
    this.parentNode.children = this.parentNode.children.filter(
      (node) => node !== this,
    )
    this.parentNode = null
    this.parentElement = null
  }

  contains(target) {
    if (target === this) return true
    return this.childNodes.some(
      (child) => child === target || (child.contains && child.contains(target)),
    )
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value))
  }

  getAttribute(name) {
    return this.attributes.get(String(name)) || null
  }

  getBoundingClientRect() {
    return { ...this.rect }
  }
}

function flattenTextNodes(root) {
  const nodes = []
  const visit = (node) => {
    if (node.nodeType === 3) {
      nodes.push(node)
      return
    }
    for (const child of node.childNodes || []) visit(child)
  }
  visit(root)
  return nodes
}

class FakeRange {
  constructor(root) {
    this.root = root
    this.startContainer = null
    this.startOffset = 0
    this.endContainer = null
    this.endOffset = 0
  }

  setStart(node, offset) {
    this.startContainer = node
    this.startOffset = offset
  }

  setEnd(node, offset) {
    this.endContainer = node
    this.endOffset = offset
  }

  cloneRange() {
    const copy = new FakeRange(this.root)
    copy.setStart(this.startContainer, this.startOffset)
    copy.setEnd(this.endContainer, this.endOffset)
    return copy
  }

  toString() {
    const nodes = flattenTextNodes(this.root)
    const startIndex = nodes.indexOf(this.startContainer)
    const endIndex = nodes.indexOf(this.endContainer)
    if (startIndex < 0 || endIndex < startIndex) return ''
    return nodes
      .slice(startIndex, endIndex + 1)
      .map((node, index, selected) => {
        const first = index === 0
        const last = index === selected.length - 1
        const start = first ? this.startOffset : 0
        const end = last ? this.endOffset : node.textContent.length
        return node.textContent.slice(start, end)
      })
      .join('')
  }

  getClientRects() {
    return [{ left: 10, top: 20, width: 80, height: 16 }]
  }

  getBoundingClientRect() {
    return this.getClientRects()[0]
  }
}

function createBridge(
  textParts,
  {
    url = 'https://example.com/guide',
    blockHighlightStyle = false,
  } = {},
) {
  const body = new FakeElement('body')
  const head = new FakeElement('head')
  body.scrollWidth = 1200
  body.scrollHeight = 4000
  for (const part of textParts) body.appendChild(new FakeTextNode(part))
  const listeners = new Map()
  const highlightMap = new Map()
  let treeWalkerCalls = 0
  let selection = {
    rangeCount: 0,
    toString: () => '',
  }
  const document = {
    body,
    head,
    documentElement: body,
    addEventListener(type, callback) {
      listeners.set(type, callback)
    },
    createElement(tagName) {
      const element = new FakeElement(tagName)
      if (String(tagName).toLowerCase() === 'style') {
        element.sheet = { cssRules: blockHighlightStyle ? [] : [{}, {}] }
      }
      return element
    },
    createRange: () => new FakeRange(body),
    createTreeWalker(root) {
      treeWalkerCalls += 1
      const nodes = flattenTextNodes(root)
      let index = -1
      return {
        nextNode() {
          index += 1
          return nodes[index] || null
        },
      }
    },
    elementFromPoint: () => null,
    getElementById: () => null,
  }
  const window = {
    location: { href: url },
    innerHeight: 800,
    innerWidth: 1200,
    scrollX: 0,
    scrollY: 0,
    addEventListener(type, callback) {
      listeners.set(type, callback)
    },
    getSelection: () => selection,
    scrollTo() {},
  }
  class FakeHighlight {
    constructor(...ranges) {
      this.ranges = ranges
    }
  }
  class FakeMutationObserver {
    constructor(callback) {
      this.callback = callback
    }

    observe() {}

    disconnect() {}
  }
  const context = {
    CSS: {
      highlights: {
        delete: (name) => highlightMap.delete(name),
        get: (name) => highlightMap.get(name),
        set: (name, value) => highlightMap.set(name, value),
      },
    },
    Highlight: FakeHighlight,
    MutationObserver: FakeMutationObserver,
    Node: { ELEMENT_NODE: 1, TEXT_NODE: 3 },
    NodeFilter: { SHOW_TEXT: 4 },
    clearTimeout() {},
    console: { log() {} },
    document,
    setTimeout: () => 1,
    window,
  }
  vm.createContext(context)
  const runBridge = (cardId) => {
    const script = bridgeTemplate
      .replace('__CARD_ID__', String(cardId))
      .replace('__PYCMD_PREFIX__', JSON.stringify('private:'))
      .replace('__MSG_PROGRESS__', JSON.stringify('progress:'))
    vm.runInContext(script, context)
  }
  runBridge(42)
  return {
    body,
    context,
    document,
    highlightMap,
    getTreeWalkerCalls: () => treeWalkerCalls,
    runBridge,
    setSelection(range, renderedText = null) {
      selection = {
        rangeCount: 1,
        getRangeAt: () => range,
        toString: () => renderedText === null ? range.toString() : renderedText,
      }
    },
    window,
  }
}

function anchor(overrides = {}) {
  return {
    version: 1,
    id: 'anchor-1',
    exact: 'faith',
    prefix: 'Keep the ',
    suffix: ' always',
    startPath: [0],
    startOffset: 9,
    endPath: [0],
    endOffset: 14,
    ...overrides,
  }
}

test('captures an exact quote, context, and DOM boundaries', () => {
  const harness = createBridge(['before selected after'])
  const textNode = harness.body.childNodes[0]
  const range = harness.document.createRange()
  range.setStart(textNode, 7)
  range.setEnd(textNode, 15)
  harness.setSelection(range)

  const capture = harness.window.incrementoCaptureExtraction()

  assert.equal(capture.url, 'https://example.com/guide')
  assert.equal(capture.cardId, 42)
  assert.equal(capture.text, 'selected')
  assert.equal(capture.anchor.exact, 'selected')
  assert.equal(capture.anchor.prefix, 'before ')
  assert.equal(capture.anchor.suffix, ' after')
  assert.deepEqual(Array.from(capture.anchor.startPath), [0])
  assert.deepEqual(Array.from(capture.anchor.endPath), [0])
  assert.deepEqual(
    JSON.parse(JSON.stringify(capture.rects)),
    [{ x: 10, y: 20, width: 80, height: 16 }],
  )
})

test('uses rendered selection text while retaining exact DOM anchor text', () => {
  const harness = createBridge(['First paragraph', 'Second paragraph'])
  const range = harness.document.createRange()
  range.setStart(harness.body.childNodes[0], 0)
  range.setEnd(harness.body.childNodes[1], 16)
  harness.setSelection(range, 'First paragraph\n\nSecond paragraph')

  const capture = harness.window.incrementoCaptureExtraction()

  assert.equal(capture.text, 'First paragraph\n\nSecond paragraph')
  assert.equal(capture.anchor.exact, 'First paragraphSecond paragraph')
  assert.equal(capture.rects.length, 1)
})

test('reinjection changes card identity and clears the prior selection cache', () => {
  const harness = createBridge(['before selected after'])
  const textNode = harness.body.childNodes[0]
  const range = harness.document.createRange()
  range.setStart(textNode, 7)
  range.setEnd(textNode, 15)
  harness.setSelection(range)
  assert.equal(harness.window.incrementoCaptureExtraction().cardId, 42)

  harness.setSelection({
    cloneRange() {
      return this
    },
    toString() {
      return ''
    },
  })
  harness.runBridge(99)

  assert.equal(harness.window.incrementoCaptureExtraction(), null)
  assert.equal(harness.window._incrementoActiveCardId, 99)
})

test('reinjection repairs a partially missing bridge API', () => {
  const harness = createBridge(['before selected after'])
  harness.window.incrementoCaptureExtraction = undefined

  harness.runBridge(99)

  assert.equal(typeof harness.window.incrementoCaptureExtraction, 'function')
  assert.equal(typeof harness.window.incrementoCaptureSnapshotAnchor, 'function')
  assert.equal(typeof harness.window.incrementoResolveExtractionRects, 'function')
  assert.equal(harness.window._incrementoActiveCardId, 99)
})

test('resolves the saved DOM path when its quote still matches', () => {
  const harness = createBridge(['Keep the faith always'])

  const range = harness.window.incrementoResolveExtractionAnchor(anchor())

  assert.equal(range.toString(), 'faith')
})

test('falls back to quote context after the original DOM path changes', () => {
  const harness = createBridge(['Keep the ', 'faith', ' always'])

  const range = harness.window.incrementoResolveExtractionAnchor(
    anchor({ startPath: [99], endPath: [99] }),
  )

  assert.equal(range.toString(), 'faith')
  assert.equal(range.startContainer, harness.body.childNodes[1])
})

test('fails closed when a repeated quote has no unique context', () => {
  const harness = createBridge(['faith and faith'])

  const range = harness.window.incrementoResolveExtractionAnchor(
    anchor({
      prefix: '',
      suffix: '',
      startPath: [99],
      endPath: [99],
      startOffset: 0,
      endOffset: 5,
    }),
  )

  assert.equal(range, null)
})

test('fails closed when a repeated quote has only one weak context character', () => {
  const harness = createBridge(['xfaith and yfaith'])

  const range = harness.window.incrementoResolveExtractionAnchor(
    anchor({
      prefix: 'x',
      suffix: '',
      startPath: [99],
      endPath: [99],
      startOffset: 0,
      endOffset: 5,
    }),
  )

  assert.equal(range, null)
})

test('indexes page text once while restoring several changed DOM anchors', () => {
  const harness = createBridge(['Keep the faith always, pending next'])
  const changedPath = { startPath: [99], endPath: [99] }

  const result = harness.window.incrementoResolveExtractionRects({
    saved: [anchor(changedPath)],
    pending: [anchor({
      ...changedPath,
      id: 'anchor-2',
      exact: 'pending',
      prefix: 'always, ',
      suffix: ' next',
      startOffset: 0,
      endOffset: 7,
    })],
  })

  assert.equal(result.markers.filter((marker) => marker.state === 'saved').length, 1)
  assert.equal(result.markers.filter((marker) => marker.state === 'pending').length, 1)
  assert.equal(harness.getTreeWalkerCalls(), 1)
})

test('returns geometry without inserting an overlay into the webpage', () => {
  const harness = createBridge(['Keep the faith always, pending next'])
  const beforeNodes = harness.body.childNodes.slice()
  const pending = anchor({
    id: 'anchor-2',
    exact: 'pending',
    prefix: 'always, ',
    suffix: ' next',
    startOffset: 23,
    endOffset: 30,
  })

  const result = harness.window.incrementoResolveExtractionRects({
    saved: [anchor()],
    pending: [pending],
  })

  assert.equal(result.markers.length, 2)
  assert.deepEqual(harness.body.childNodes, beforeNodes)
  assert.equal('_incrementoExtractionOverlayRoot' in harness.window, false)
  assert.equal(harness.highlightMap.size, 0)
})

test('geometry resolution does not depend on page highlight styles or CSP', () => {
  const harness = createBridge(
    ['Keep the faith always'],
    { blockHighlightStyle: true },
  )

  const result = harness.window.incrementoResolveExtractionRects({
    saved: [anchor()],
    pending: [],
  })

  assert.equal(result.markers.length, 1)
  assert.equal(harness.highlightMap.size, 0)
  assert.equal('_incrementoExtractionOverlayRoot' in harness.window, false)
})

test('captures and resolves a snapshot region anchored to the hit element', () => {
  const harness = createBridge(['page text'])
  const article = new FakeElement('article')
  article.rect = { left: 100, top: 50, width: 400, height: 200 }
  harness.body.appendChild(article)
  harness.document.elementFromPoint = () => article
  harness.window.scrollY = 500

  const capture = harness.window.incrementoCaptureSnapshotAnchor({
    x: 140,
    y: 80,
    width: 200,
    height: 100,
  })

  assert.equal(capture.cardId, 42)
  assert.equal(capture.url, 'https://example.com/guide')
  assert.deepEqual(Array.from(capture.anchor.anchorPath), [0])
  assert.equal(capture.anchor.kind, 'snapshot')
  assert.equal(capture.anchor.pageX, 140)
  assert.equal(capture.anchor.pageY, 580)
  assert.equal(capture.anchor.anchorTag, 'article')
  assert.equal(capture.anchor.anchorXRatio, 350000)
  assert.equal(capture.anchor.anchorYRatio, 400000)

  capture.anchor.id = 'snapshot-1'
  const result = harness.window.incrementoResolveExtractionRects({
    saved: [capture.anchor],
    pending: [],
  })

  assert.equal(result.markers.length, 1)
  assert.equal(result.markers[0].kind, 'snapshot')
  assert.deepEqual(
    JSON.parse(JSON.stringify(result.markers[0].rects)),
    [{ x: 140, y: 580, width: 200, height: 100 }],
  )

  article.rect = { left: 100, top: 150, width: 400, height: 200 }
  const moved = harness.window.incrementoResolveExtractionRects({
    saved: [capture.anchor],
    pending: [],
  })
  assert.deepEqual(
    JSON.parse(JSON.stringify(moved.markers[0].rects)),
    [{ x: 140, y: 680, width: 200, height: 100 }],
  )
})

test('uses bounded page coordinates if a snapshot DOM path no longer resolves', () => {
  const harness = createBridge(['page text'])
  harness.window.scrollX = 20
  harness.window.scrollY = 500
  const snapshot = {
    version: 1,
    id: 'snapshot-fallback',
    kind: 'snapshot',
    pageX: 140,
    pageY: 580,
    width: 200,
    height: 100,
    documentWidth: 1200,
    documentHeight: 4000,
    anchorPath: [99],
    anchorTag: 'article',
    anchorXRatio: 350000,
    anchorYRatio: 400000,
  }

  const result = harness.window.incrementoResolveExtractionRects({
    saved: [],
    pending: [snapshot],
  })

  assert.equal(result.markers.length, 1)
  assert.equal(result.markers[0].state, 'pending')
  assert.deepEqual(
    JSON.parse(JSON.stringify(result.markers[0].rects)),
    [{ x: 140, y: 580, width: 200, height: 100 }],
  )
})

test('resolves native document geometry without changing the webpage DOM', () => {
  const harness = createBridge(['Keep the faith always, pending next'])
  harness.window.scrollX = 5
  harness.window.scrollY = 400
  const beforeNodes = harness.body.childNodes.slice()

  const result = harness.window.incrementoResolveExtractionRects({
    saved: [anchor()],
    pending: [anchor({
      id: 'anchor-2',
      exact: 'pending',
      prefix: 'always, ',
      suffix: ' next',
      startOffset: 23,
      endOffset: 30,
    })],
  })

  assert.equal(result.cardId, 42)
  assert.equal(result.url, 'https://example.com/guide')
  assert.equal(result.scrollX, 5)
  assert.equal(result.scrollY, 400)
  assert.deepEqual(
    JSON.parse(JSON.stringify(result.markers)),
    [
      {
        id: 'anchor-1',
        state: 'saved',
        kind: 'text',
        rects: [{ x: 15, y: 420, width: 80, height: 16 }],
      },
      {
        id: 'anchor-2',
        state: 'pending',
        kind: 'text',
        rects: [{ x: 15, y: 420, width: 80, height: 16 }],
      },
    ],
  )
  assert.deepEqual(harness.body.childNodes, beforeNodes)
  assert.equal('_incrementoExtractionOverlayRoot' in harness.window, false)
})
