/** Same reading UI and saved document data; navigation stays local to each pane. */
export function pdfReaderGroups(readingOnly = false) {
  return readingOnly ? ['navigation', 'reading', 'annotation']
    : ['navigation', 'reading', 'annotation', 'review'];
}

export function sharedPdfReaderStartup(config) {
  const limitStatus = config.limit_status || (config.max_page < 1_000_000
    ? {enabled: true, enforcement_mode: 'hard_stop', allowed_max_page: config.max_page}
    : {enabled: false});
  return {
    highlights: config.highlights || [],
    pending: {
      cardId: config.card_id, filename: config.filename, page: config.page,
      zoom: config.zoom || 1, scrollRatio: config.scroll_ratio || 0,
      pageY: config.page_y, readPage: config.read_page || 0, readAnchor: config.read_anchor,
      jumpExcerpt: config.excerpt || '', bookmarks: config.bookmarks || [],
      locale: config.locale, customLanguage: config.custom_language,
      appearanceMode: config.appearance || 'original', limitStatus,
      autoHighlightOnExtract: config.auto_highlight !== false,
      scrollToTopOnPageChange: config.scroll_to_top !== false,
      showHighlightDeleteButtons: config.show_delete !== false,
      linkPreviewZoom: config.link_preview_zoom,
      controlsCollapsed: config.controls_collapsed,
    },
  };
}
