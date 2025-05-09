export const ENUMS = {
  "STAFF_ROLE": {
    scenario: "Scenario",
    director: "Director",
    chardesign: "Character design",
    art: "Artist",
    music: "Composer",
    songs: "Vocals",
    translator: "Translator",
    editor: "Editor",
    qa: "Quality assurance",
    staff: "Staff"
  },
  'RELATION': {
    ser: "Same series",
    char: "Shares characters",
    alt: "Alternative version",
    preq: "Prequel",
    seq: "Sequel",
    side: "Side story",
    set: "Same setting",
    fan: "Fandisc",
    orig: "Original game",
  },
  "MEDIUM": {
    blr: "Blu-ray disc",
    mrt: "Cartridge",
    cas: "Cassette tape",
    cd: "CD",
    dc: "Download card",
    dvd: "DVD",
    flp: "Floppy",
    gdr: "GD-ROM",
    in: "Internet download",
    mem: "Memory card",
    nod: "Nintendo Optical Disc",
    umd: "UMD",
    otc: "Other"
  },
  "LANGUAGE": {
    ar: "Arabic",
    eu: "Basque",
    be: "Belarusian",
    bg: "Bulgarian",
    ca: "Catalan",
    ck: "Cherokee",
    zh: "Chinese",
    "zh-Hans": "Chinese (simplified)",
    "zh-Hant": "Chinese (traditional)",
    hr: "Croatian",
    cs: "Czech",
    da: "Danish",
    nl: "Dutch",
    en: "English",
    eo: "Esperanto",
    fi: "Finnish",
    fr: "French",
    gl: "Galician",
    de: "German",
    el: "Greek",
    he: "Hebrew",
    hi: "Hindi",
    hu: "Hungarian",
    ga: "Irish",
    id: "Indonesian",
    it: "Italian",
    iu: "Inuktitut",
    ja: "Japanese",
    kk: "Kazakh",
    ko: "Korean",
    la: "Latin",
    lv: "Latvian",
    lt: "Lithuanian",
    mk: "Macedonian",
    ms: "Malay",
    ne: "Nepali",
    no: "Norwegian",
    fa: "Persian",
    pl: "Polish",
    "pt-br": "Portuguese (Brazil)",
    "pt-pt": "Portuguese (Portugal)",
    ro: "Romanian",
    ru: "Russian",
    gd: "Scottish Gaelic",
    sr: "Serbian",
    sk: "Slovak",
    sl: "Slovene",
    es: "Spanish",
    sv: "Swedish",
    ta: "Tagalog",
    th: "Thai",
    tr: "Turkish",
    uk: "Ukrainian",
    ur: "Urdu",
    vi: "Vietnamese"
  },
  "PLATFORM": {
    win: "Windows",
    lin: "Linux",
    mac: "Mac OS",
    web: "Website",
    tdo: "3DO",
    ios: "Apple iProduct",
    and: "Android",
    bdp: "Blu-ray Player",
    dos: "DOS",
    dvd: "DVD Player",
    drc: "Dreamcast",
    nes: "Famicom",
    sfc: "Super Famicom",
    fm7: "FM-7",
    fm8: "FM-8",
    fmt: "FM Towns",
    gba: "Game Boy Advance",
    gbc: "Game Boy Color",
    msx: "MSX",
    nds: "Nintendo DS",
    swi: "Nintendo Switch",
    wii: "Nintendo Wii",
    wiu: "Nintendo Wii U",
    n3d: "Nintendo 3DS",
    p88: "PC-88",
    p98: "PC-98",
    pce: "PC Engine",
    pcf: "PC-FX",
    psp: "PlayStation Portable",
    ps1: "PlayStation 1",
    ps2: "PlayStation 2",
    ps3: "PlayStation 3",
    ps4: "PlayStation 4",
    ps5: "PlayStation 5",
    psv: "PlayStation Vita",
    smd: "Sega Mega Drive",
    scd: "Sega Mega-CD",
    sat: "Sega Saturn",
    vnd: "VNDS",
    x1s: "Sharp X1",
    x68: "Sharp X68000",
    xb1: "Xbox",
    xb3: "Xbox 360",
    xbo: "Xbox One",
    xxs: "Xbox X/S",
    mob: "Other (mobile)",
    oth: "Other"
  },
  "LENGTH": {
    1: "Very Short",
    2: "Short",
    3: "Medium",
    4: "Long",
    5: "Very Long",
  },
  "DEVSTATUS": {
    0: "Finished",
    1: "In Development",
    2: "Cancelled",
  },
  "VOICED": {
    1: "Not voiced",
    2: "Only ero scenes voiced",
    3: "Partially voiced",
    4: "Fully voiced",
  },
  "RTYPE": {
    trial: "Trial",
    partical: "Partical",
    complete: "Complete",
  },
  "CHARACTER_ROLE": {
    main: "Protagonist",
    primary: "Main Character",
    side: "Side Character",
    appears: "Appears",
  },
  "TYPE": {
    co: "Company",
    in: "Individual",
    ng: "Amateur Group",
  },
  "CATEGORY": {
    cont: "Content",
    ero: "Sexual Content",
    tech: "Technical",
  }
} as const

type StaffRole = keyof typeof ENUMS.STAFF_ROLE
type Medium = keyof typeof ENUMS.MEDIUM
type Language = keyof typeof ENUMS.LANGUAGE
type Platform = keyof typeof ENUMS.PLATFORM
type Length = keyof typeof ENUMS.LENGTH
type DevStatus = keyof typeof ENUMS.DEVSTATUS
type Voiced = keyof typeof ENUMS.VOICED
type RType = keyof typeof ENUMS.RTYPE
type CharacterRole = keyof typeof ENUMS.CHARACTER_ROLE
type Type = keyof typeof ENUMS.TYPE
type Category = keyof typeof ENUMS.CATEGORY

export type { StaffRole, Medium, Language, Platform, Length, DevStatus, Voiced, RType, CharacterRole, Type, Category }
