import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    visible: true
    title: "mergen · " + root.s.version
    width: 580; height: 560
    minimumWidth: 560
    minimumHeight: tabs.currentIndex === 0 ? Math.max(440, Math.ceil(mainColumn.implicitHeight + root.footer.implicitHeight + 40)) : 520
    font.capitalization: Font.AllLowercase
    property bool usageVisible: root.s.showUsage
    function compactMain() {
        if (tabs.currentIndex === 0)
            root.height = root.minimumHeight
    }
    onUsageVisibleChanged: Qt.callLater(root.compactMain)
    onMinimumHeightChanged: Qt.callLater(root.compactMain)
    Component.onCompleted: Qt.callLater(root.compactMain)
    font.family: "Segoe UI"
    font.pixelSize: 13
    property var s: controller.state
    property var themes: ({
        green: ["#16201c","#202c25","#ecf2ed","#9fb1a4","#bbd9c4","#c3b5df"],
        white: ["#f7f8fa","#ffffff","#172033","#738094","#0878ed","#0878ed"],
        navy: ["#171e2b","#202a3a","#eef1f8","#a0adc2","#a8bfe8","#d5b99b"],
        black: ["#191a1d","#232529","#f1f1f3","#a4a6af","#d9dbe2","#aabbdc"],
        sepia: ["#f2eee7","#fbf8f2","#39322a","#82796d","#705640","#596c86"]
    })
    property var paletteColors: themes[s.theme] || themes.white
    property color bg: paletteColors[0]
    property color surface: paletteColors[1]
    property color fg: paletteColors[2]
    property color muted: paletteColors[3]
    property color accent: paletteColors[4]
    property color opposite: paletteColors[5]
    property bool lightTheme: s.theme === "white" || s.theme === "sepia"
    property color buttonInk: lightTheme ? "#ffffff" : "#19212c"
    property color line: Qt.rgba(root.muted.r,root.muted.g,root.muted.b,root.lightTheme ? .16 : .18)
    property color field: lightTheme ? Qt.darker(surface,1.035) : Qt.lighter(bg,1.18)
    color: bg
    palette.window: bg; palette.windowText: fg; palette.text: fg
    palette.base: surface; palette.button: surface; palette.buttonText: fg
    palette.highlight: opposite; palette.highlightedText: bg
    onClosing: function(close) { close.accepted = false; controller.action("quit") }

    background: Rectangle { color: root.bg }
    component Glyph: Image {
        property string name: ""
        property color ink: root.fg
        width: 20; height: 20
        fillMode: Image.PreserveAspectFit
        source: "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="'+ink+'" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+({
            region:'<path stroke-dasharray="3 3" d="M4 4h16v16H4z"/>',
            full:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
            refresh:'<path d="M20 8a8 8 0 0 0-14-2L3 9m0-5v5h5m-4 7a8 8 0 0 0 14 2l3-3m0 5v-5h-5"/>',
            eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
            settings:'<path d="M19.02 9.99L21.13 10.23L21.13 13.77L19.02 14.01L18.38 15.54L19.71 17.20L17.20 19.71L15.54 18.38L14.01 19.02L13.77 21.13L10.23 21.13L9.99 19.02L8.46 18.38L6.80 19.71L4.29 17.20L5.62 15.54L4.98 14.01L2.87 13.77L2.87 10.23L4.98 9.99L5.62 8.46L4.29 6.80L6.80 4.29L8.46 5.62L9.99 4.98L10.23 2.87L13.77 2.87L14.01 4.98L15.54 5.62L17.20 4.29L19.71 6.80L18.38 8.46Z"/><circle cx="12" cy="12" r="3.1"/>',
            play:'<path fill="'+ink+'" stroke="none" d="m7 3 15 9-15 9z"/>',
            stop:'<rect x="5" y="5" width="14" height="14" rx="2"/>',
            globe:'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
            sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
            moon:'<path d="M20.7 13.2A8.7 8.7 0 0 1 10.8 3.3a8.7 8.7 0 1 0 9.9 9.9Z"/>',
            puzzle:'<path d="M4 4h6a3 3 0 1 1 4 0h6v6a3 3 0 1 0 0 4v6h-6a3 3 0 1 0-4 0H4v-6a3 3 0 1 1 0-4z"/>'
        }[name] || '')+'</svg>')
    }

    component LabelText: Label { font.capitalization: Font.AllLowercase; color: root.fg; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    component Quiet: LabelText { color: root.muted; font.pixelSize: 12 }
    component IconAction: Button {
        id: iconButton
        property string iconName: ""
        property string hint: ""
        implicitWidth: 44; implicitHeight: 44
        padding: 11
        Accessible.name: hint
        contentItem: Glyph { name: iconButton.iconName; ink: iconButton.checked ? root.accent : root.muted }
        background: Rectangle {
            radius: 10
            color: iconButton.checked ? Qt.rgba(root.accent.r,root.accent.g,root.accent.b,.10) : iconButton.down || iconButton.hovered ? root.field : "transparent"
            border.color: iconButton.activeFocus ? root.accent : "transparent"
            Behavior on color { ColorAnimation { duration: 140 } }
        }
        ToolTip {
            visible: iconButton.hovered; delay: 450
            x: iconButton.width + 8; y: (iconButton.height-height)/2
            contentItem: Text { text: iconButton.hint; color: root.fg; font: root.font }
            background: Rectangle { color: root.surface; radius: 8; border.color: root.line }
        }
    }
    component Action: Button {
        id: actionButton
        property string iconName: ""
        implicitHeight: 46
        font.pixelSize: 13
        opacity: enabled ? 1 : .48
        contentItem: RowLayout {
            spacing: actionButton.text === "" ? 0 : 9
            Item { Layout.fillWidth: true }
            Glyph { name: actionButton.iconName; visible: name !== ""; ink: root.muted; Layout.minimumWidth: 18; Layout.minimumHeight: 18; Layout.preferredWidth: 18; Layout.preferredHeight: 18; Layout.maximumWidth: 18; Layout.maximumHeight: 18 }
            Text { visible: text !== ""; font.family: root.font.family; font.pixelSize: 13; font.capitalization: Font.AllLowercase; text: actionButton.text; color: root.fg; elide: Text.ElideRight; Layout.maximumWidth: Math.max(0, actionButton.width - (actionButton.iconName ? 54 : 24)) }
            Item { Layout.fillWidth: true }
        }
        background: Rectangle {
            radius: 10
            color: actionButton.down ? root.field : actionButton.hovered ? Qt.lighter(root.surface,root.lightTheme ? .98 : 1.16) : root.surface
            border.width: parent.activeFocus ? 2 : 1
            border.color: parent.activeFocus ? root.accent : root.line
            Behavior on color { ColorAnimation { duration: 100 } }
        }
    }
    component Select: ComboBox {
        id: select
        opacity: enabled ? 1 : .48
        onEnabledChanged: if (!enabled) popup.close()
        font.capitalization: Font.AllLowercase
        wheelEnabled: false
        Layout.fillWidth: true
        implicitHeight: 46
        indicator: Item {
            x: select.width-width-14; y: (select.height-height)/2; width: 14; height: 16
            Rectangle { x: 1; y: 5; width: 7; height: 2; radius: 1; color: root.muted; rotation: 45; transformOrigin: Item.Left; antialiasing: true }
            Rectangle { x: 6; y: 10; width: 7; height: 2; radius: 1; color: root.muted; rotation: -45; transformOrigin: Item.Left; antialiasing: true }
        }
        background: Rectangle { color: root.field; radius: 9; border.color: parent.activeFocus ? root.accent : "transparent" }
        delegate: ItemDelegate {
            required property int index
            required property var modelData
            width: select.width
            height: 42
            highlighted: select.highlightedIndex === index
            contentItem: Text { text: String(parent.modelData).replace(/\u0130/g, "i").toLowerCase(); font: select.font; color: root.fg; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 12; rightPadding: 12 }
            background: Rectangle { radius: 6; color: parent.highlighted ? root.field : root.surface }
        }
        popup: Popup {
            y: select.height + 6; width: select.width; padding: 6
            implicitHeight: Math.min(contentItem.implicitHeight + 12, 290)
            background: Rectangle { color: root.surface; radius: 10; border.color: root.line }
            contentItem: ListView { clip: true; implicitHeight: contentHeight; model: select.popup.visible ? select.delegateModel : null; currentIndex: select.highlightedIndex; ScrollIndicator.vertical: ScrollIndicator {} }
        }
        contentItem: Text { text: String(select.displayText).replace(/\u0130/g, "i").toLowerCase(); font: select.font; color: root.fg; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 12; rightPadding: 24 }
    }
    component Panel: Frame {
        property bool flat: false
        Layout.fillWidth: true
        padding: flat ? 0 : 18
        background: Rectangle {
            radius: 12
            color: parent.flat ? "transparent" : root.surface
            border.color: parent.flat ? "transparent" : root.line
        }
    }
    component ThemeScrollBar: ScrollBar {
        id: scrollBar
        implicitWidth: 6
        padding: 0
        contentItem: Rectangle {
            implicitWidth: 6; implicitHeight: 30; radius: 3
            color: scrollBar.pressed ? root.accent : root.muted
            opacity: scrollBar.pressed || scrollBar.hovered ? .65 : .28
        }
        background: Item {}
    }
    component ThemeScrollView: ScrollView {
        id: scrollView
        clip: true; contentWidth: availableWidth
        rightPadding: 10
        ScrollBar.vertical: ThemeScrollBar {
            parent: scrollView
            x: scrollView.width - width; y: scrollView.topPadding
            height: scrollView.availableHeight
            visible: size < 1
        }
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    }
    component ThemeProgress: ProgressBar {
        id: meter
        implicitHeight: 5
        padding: 0
        background: Rectangle { implicitHeight: 5; radius: height / 2; color: root.line }
        contentItem: Item {
            clip: true; implicitHeight: 5
            Rectangle {
                id: fill
                property real offset: 0
                height: parent.height; radius: height / 2; color: root.accent
                width: meter.indeterminate ? parent.width * .24 : parent.width * meter.visualPosition
                x: meter.indeterminate ? offset : 0
                NumberAnimation on offset {
                    running: meter.visible && meter.indeterminate
                    from: -fill.width; to: meter.width; duration: 1300; loops: Animation.Infinite
                }
            }
        }
    }
    component Toggle: CheckBox {
        id: check
        Layout.fillWidth: true; implicitHeight: 36; font.pixelSize: 13
        indicator: Rectangle {
            x: check.width-width; y: (check.height-height)/2; width: 40; height: 22; radius: 11
            color: check.checked ? root.accent : root.field
            border.color: check.activeFocus ? root.accent : root.line
            Rectangle {
                x: check.checked ? 21 : 3; y: 3; width: 16; height: 16; radius: 8
                color: check.checked ? root.buttonInk : root.muted
                Behavior on x { NumberAnimation { duration: 120 } }
            }
        }
        contentItem: Text { text: check.text; font: check.font; color: root.fg; rightPadding: 54; verticalAlignment: Text.AlignVCenter; wrapMode: Text.WordWrap }
    }
    component ThemeSlider: Slider {
        id: slider
        Layout.fillWidth: true; implicitHeight: 34
        background: Rectangle {
            x: slider.leftPadding; y: (slider.height-height)/2
            width: slider.availableWidth; height: 5; radius: 3
            color: Qt.rgba(root.opposite.r,root.opposite.g,root.opposite.b,.25)
            Rectangle { width: slider.visualPosition*parent.width; height: parent.height; radius: 3; color: root.opposite }
        }
        handle: Rectangle {
            x: slider.leftPadding + slider.visualPosition*(slider.availableWidth-width)
            y: (slider.height-height)/2; width: 22; height: 22; radius: 11
            color: root.surface; border.color: root.opposite; border.width: 2
        }
    }
    component NumberSelect: SpinBox {
        id: numberSelect
        wheelEnabled: false; implicitWidth: 122; implicitHeight: 40
        leftPadding: 36; rightPadding: 36
        contentItem: Text { text: numberSelect.value; color: root.fg; font: numberSelect.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 9; color: root.field; border.color: numberSelect.activeFocus ? root.accent : "transparent" }
        down.indicator: Rectangle { x: 0; height: parent.height; width: 34; radius: 12; color: numberSelect.down.pressed ? root.surface : "transparent"; Text { anchors.centerIn: parent; text: "−"; color: root.fg; font.pixelSize: 19 } }
        up.indicator: Rectangle { x: parent.width-width; height: parent.height; width: 34; radius: 12; color: numberSelect.up.pressed ? root.surface : "transparent"; Text { anchors.centerIn: parent; text: "+"; color: root.fg; font.pixelSize: 19 } }
    }

    // Keep controller page indices stable: translation, settings, models, updates.
    QtObject { id: tabs; property int currentIndex: 0; onCurrentIndexChanged: Qt.callLater(root.compactMain) }
    Rectangle {
        id: sidebar
        objectName: "navigationRail"
        width: 72; anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: root.surface
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: root.line }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 14; spacing: 8
            Image {
                objectName: "railLogo"
                source: "../../../assets/mergen-logo.png"; fillMode: Image.PreserveAspectFit
                sourceSize: Qt.size(256,256)
                smooth: true; mipmap: true
                Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 12; Layout.bottomMargin: 24
                Layout.preferredWidth: 32; Layout.preferredHeight: 32
                Accessible.name: "mergen"
            }
            Repeater {
                model: [{label:"çeviri",icon:"region",page:0},{label:"modeller",icon:"puzzle",page:2},{label:"ayarlar",icon:"settings",page:1},{label:"güncellemeler",icon:"refresh",page:3}]
                IconAction {
                    required property var modelData
                    objectName: "nav_" + modelData.page
                    Layout.fillWidth: true
                    iconName: modelData.icon; hint: modelData.label
                    checked: tabs.currentIndex === modelData.page
                    onClicked: tabs.currentIndex = modelData.page
                }
            }
            Item { Layout.fillHeight: true }
            IconAction {
                objectName: "themeToggle"
                Layout.fillWidth: true; Layout.bottomMargin: 4
                iconName: root.lightTheme ? "moon" : "sun"
                hint: root.lightTheme ? "koyu görünüme geç" : "açık görünüme geç"
                onClicked: controller.setting("panel_theme",root.lightTheme ? "black" : "white")
            }
        }
    }
    Connections {
        target: controller
        function onNavigate(index) { tabs.currentIndex = index }
        function onConfirmation(title, message) { confirmDialog.title = title; confirmationText.text = message; confirmDialog.open() }
    }
    Dialog {
        id: confirmDialog
        modal: true; anchors.centerIn: parent; width: Math.min(root.width - 40, 440)
        footer: RowLayout {
            spacing: 10
            Action { text: "vazgeç"; Layout.fillWidth: true; onClicked: confirmDialog.reject() }
            Action { text: "devam et"; Layout.fillWidth: true; onClicked: confirmDialog.accept() }
        }
        onAccepted: controller.confirm(true)
        onRejected: controller.confirm(false)
        contentItem: Label { id: confirmationText; wrapMode: Text.WordWrap; color: root.fg }
        background: Rectangle { radius: 12; color: root.surface; border.color: root.line }
    }
    StackLayout {
        anchors.left: sidebar.right; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.margins: 20
        currentIndex: tabs.currentIndex
        ColumnLayout {
            id: mainColumn
            spacing: 12
            ColumnLayout {
                id: primaryColumn
                Layout.fillWidth: true; spacing: 10
                Panel {
                    flat: true
                    ColumnLayout {
                        width: parent.width; spacing: 10
                        Quiet { text: "Kaynak dil"; font.pixelSize: 13 }
                        Select {
                            objectName: "languageSelect"
                            enabled: root.s.languageSelectable
                            model: ["Japonca · Manga", "Korece · Manhwa / Webtoon", "Çince Basit · Manhua", "Çince Geleneksel · Manhua", "İngilizce · Çizgi roman"]
                            currentIndex: ["ja","ko","zh","zh_tw","en"].indexOf(root.s.language)
                            onActivated: controller.setting("source_lang", ["ja","ko","zh","zh_tw","en"][currentIndex])
                        }
                    }
                }
                Quiet { text: "Çeviri alanı" }
                GridLayout {
                    objectName: "translationActions"
                    Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 8
                    uniformCellWidths: true; uniformCellHeights: true
                    Action { objectName: "selectRegionAction"; text: "Bölge seç"; iconName: "region"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: controller.action("region") }
                    Action { objectName: "fullScreenAction"; text: "Tüm ekran"; iconName: "full"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: controller.action("full") }
                    Action { objectName: "translateOnceAction"; text: "Şimdi çevir"; iconName: "refresh"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: controller.action("once") }
                    Action { objectName: "toggleOverlayAction"; text: "Gizle / Göster"; iconName: "eye"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: controller.action("overlay") }
                }
                Toggle { text: "Kaydırmayı takip et"; checked: root.s.scrollTracking; onClicked: controller.setting("scroll_tracking",checked) }
                RowLayout {
                    Quiet { text: root.s.model === "600m" ? "nllb 600m · standart" : "nllb 1.3b · mergen bağlam v1" }
                    Label { text: ({cpu:"CPU",nvidia:"NVIDIA CUDA",amd:"AMD ROCm",intel:"Intel XPU"})[root.s.translationBackend] || "CPU"; color: root.muted; font.pixelSize: 12 }
                }
                Button {
                    id: startButton
                    objectName: "startButton"
                    text: root.s.running ? "Çeviriyi durdur" : "Çeviriyi başlat"
                    Layout.fillWidth: true; implicitHeight: 58
                    opacity: enabled ? 1 : .55
                    contentItem: RowLayout {
                        spacing: 12
                        Item { Layout.fillWidth: true }
                        Glyph { name: root.s.running ? "stop" : "play"; ink: root.buttonInk; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                        Text { font.family: root.font.family; font.capitalization: Font.AllLowercase; text: startButton.text; font.pixelSize: 16; font.weight: Font.DemiBold; color: root.buttonInk }
                        Item { Layout.fillWidth: true }
                    }
                    background: Rectangle {
                        radius: 10; color: startButton.down ? Qt.darker(root.accent,1.14) : startButton.hovered ? Qt.lighter(root.accent,1.12) : root.accent
                        border.width: startButton.activeFocus ? 2 : 0; border.color: root.opposite
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    enabled: !root.s.busy
                    onClicked: controller.action("start")
                }
            }
            Quiet { text: "Ctrl + Alt + T · Başlat / Durdur"; horizontalAlignment: Text.AlignRight }
            Panel {
                    id: usageContent
                    objectName: "usagePanel"
                    visible: root.s.showUsage
                    padding: 12
                    Layout.minimumHeight: implicitHeight
                    Layout.maximumHeight: implicitHeight
                    RowLayout {
                        width: parent.width; spacing: 16
                        Repeater {
                            model: ["gpu","vram","cpu"]
                            ColumnLayout {
                                required property string modelData
                                objectName: "usageMetric_" + modelData
                                Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 8
                                visible: modelData === "gpu" ? root.s.showGpu : modelData === "vram" ? root.s.showVram : root.s.showCpu
                                RowLayout {
                                    Layout.fillWidth: true
                                    Quiet { text: modelData; font.pixelSize: 11 }
                                    Label { text: root.s.usage[modelData]; color: root.fg; font.pixelSize: 12; font.weight: Font.DemiBold }
                                }
                                ThemeProgress {
                                    Layout.fillWidth: true; from: 0; to: 100; value: parseInt(root.s.usage[modelData]) || 0
                                }
                            }
                        }
                    }
            }
            Item { Layout.fillHeight: true; Layout.minimumHeight: 0; implicitHeight: 0 }
        }
        ThemeScrollView {
            ColumnLayout {
                width: parent.width; spacing: 14
                Panel {
                    ColumnLayout {
                        width: parent.width; spacing: 8
                        LabelText { text: "görünüm"; font.pixelSize: 18 }
                        Select { objectName: "themeSelect"; model: ["yeşil","beyaz","lacivert","siyah","sepya"]; currentIndex: ["green","white","navy","black","sepia"].indexOf(root.s.theme); onActivated: controller.setting("panel_theme",["green","white","navy","black","sepia"][currentIndex]) }
                        Quiet { text: "çeviri kutusu opaklığı" }
                        ThemeSlider { objectName: "opacitySlider"; from: .3; to: 1; value: root.s.opacity; onMoved: controller.setting("overlay_opacity", value) }
                        Quiet { text: "yazı tipi" }
                        Select { model: ["Segoe UI","Comic Sans MS","Arial"]; currentIndex: model.indexOf(root.s.fontFamily); onActivated: controller.setting("font_family",model[currentIndex]) }
                        RowLayout { Quiet { text: "en büyük yazı boyutu" } NumberSelect { from: 10; to: 96; value: root.s.maxFont; onValueModified: controller.setting("max_font_px",value) } }
                        Toggle { text: "kalın yazı"; checked: root.s.bold; onClicked: controller.setting("font_bold",checked) }
                    }
                }
                Panel {
                    ColumnLayout {
                        width: parent.width; spacing: 8
                        LabelText { text: "çalışma ortamları"; font.pixelSize: 18 }
                        Quiet { text: "hız modu" }
                        Select { model: ["hızlı","dengeli","kaliteli"]; currentIndex: ["fast","balanced","quality"].indexOf(root.s.preset); onActivated: controller.setting("speed_preset",["fast","balanced","quality"][currentIndex]) }
                        Quiet { text: "amd ve intel seçenekleri deneyseldir. önce ilgili bileşenleri kurup model testini çalıştır." }
                        Quiet { text: "çeviri" }
                        Select { model: ["cpu","nvidia cuda","amd rocm · deneysel","intel xpu · deneysel"]; currentIndex: ["cpu","nvidia","amd","intel"].indexOf(root.s.translationBackend); onActivated: controller.setting("translation_backend",["cpu","nvidia","amd","intel"][currentIndex]) }
                        Quiet { text: "paddleocr" }
                        Select { model: ["cpu","nvidia cuda","amd rocm · deneysel","intel xpu · deneysel"]; currentIndex: ["cpu","nvidia","amd","intel"].indexOf(root.s.ocrBackend); onActivated: controller.setting("ocr_backend",["cpu","nvidia","amd","intel"][currentIndex]) }
                        Toggle { text: "japonca için manga-ocr kullan"; checked: root.s.mangaEnabled; onClicked: controller.setting("use_manga_ocr",checked) }
                        Quiet { text: "manga-ocr çalışma ortamı"; visible: root.s.mangaEnabled }
                        Select { visible: root.s.mangaEnabled; model: ["cpu","nvidia cuda","amd rocm · deneysel","intel xpu · deneysel"]; currentIndex: ["cpu","nvidia","amd","intel"].indexOf(root.s.mangaBackend); onActivated: controller.setting("manga_backend",["cpu","nvidia","amd","intel"][currentIndex]) }
                        Quiet { text: "çeviri modeli" }
                        Select { model: ["nllb 600m · standart","nllb 1.3b · mergen bağlam v1"]; currentIndex: root.s.model === "600m" ? 0 : 1; onActivated: controller.setting("translation_model",currentIndex === 0 ? "nllb-200-distilled-600M-ct2" : "nllb-1.3b-baglam-v3") }
                        Toggle { text: "oturum bağlamını kullan"; checked: root.s.contextEnabled; onClicked: controller.setting("session_context",checked) }
                        Quiet { visible: root.s.model === "1300m"; text: "bağlam açıkken son üç replik kullanılır. bu sürümün uyarlama eğitimi ingilizce–türkçe için yapıldı." }
                        Action { text: "seçili ortamları doğrula"; Layout.fillWidth: true; enabled: root.s.operationAvailable; onClicked: controller.action("validate") }
                        Quiet { text: root.s.validationSummary }
                        Repeater { model: root.s.validation; delegate: Quiet { required property var modelData; text: modelData.title + " · " + modelData.message + (modelData.result ? " · " + modelData.result : ""); color: modelData.status === "passed" ? root.fg : root.muted } }
                    }
                }
                Panel {
                    ColumnLayout {
                        width: parent.width
                        LabelText { text: "okuma"; font.pixelSize: 18 }
                        Toggle { text: "kaydırmayı takip et"; checked: root.s.scrollTracking; onClicked: controller.setting("scroll_tracking",checked) }
                        Toggle { objectName: "shareTranslationsToggle"; text: "Çevirileri ekran paylaşımında göster"; checked: root.s.shareTranslations; onClicked: controller.setting("share_translations",checked) }
                        Quiet { text: "tüm ekran paylaşımında çeviri katmanı görünür. bu ayarı değiştirmek için çeviriyi durdur." }
                        Toggle { text: "çinceyi ingilizce üzerinden çevir"; checked: root.s.chinesePivot; onClicked: controller.setting("chinese_translation_via_english",checked) }
                    }
                }
                Panel {
                    ColumnLayout {
                        width: parent.width; spacing: 6
                        LabelText { text: "sistem kullanımı"; font.pixelSize: 18 }
                        Quiet { text: "ana menüde görmek istediğin göstergeleri aç. tümü kapalıyken ölçüm yapılmaz." }
                        Toggle { text: "gpu"; checked: root.s.showGpu; onClicked: controller.setting("show_gpu_usage",checked) }
                        Toggle { text: "vram"; checked: root.s.showVram; onClicked: controller.setting("show_vram_usage",checked) }
                        Toggle { text: "cpu"; checked: root.s.showCpu; onClicked: controller.setting("show_cpu_usage",checked) }
                    }
                }
                Action { text: "konuşma hafızasını temizle"; Layout.fillWidth: true; onClicked: controller.action("clear-context") }
            }
        }
        ThemeScrollView {
            ColumnLayout {
                width: parent.width; spacing: 12
                Quiet { text: root.s.hardware }
                Quiet { text: root.s.recommendation }
                Action { text: "donanımı tara ve uygun kütüphaneleri kur"; Layout.fillWidth: true; enabled: root.s.operationAvailable; onClicked: controller.action("automatic-setup") }
                Quiet { text: "gerekli çalışma kütüphaneleri internetten indirilir. ekran kartı kurulumu veya model testi geçmezse cpu ile devam edilir." }
                Panel {
                    id: operationPanel
                    objectName: "operationPanel"
                    property bool logExpanded: false
                    ColumnLayout {
                        width: parent.width; spacing: 8
                        LabelText { text: root.s.operationTitle; font.weight: Font.DemiBold }
                        Quiet { text: root.s.phase }
                        ThemeProgress { Layout.fillWidth: true; visible: root.s.busy; indeterminate: root.s.progress < 0; from: 0; to: 100; value: Math.max(0,root.s.progress) }
                        Quiet { text: root.s.validationSummary }
                        Repeater { model: root.s.validation; delegate: Quiet { required property var modelData; text: modelData.title + " · " + modelData.message + (modelData.result ? " · " + modelData.result : "") } }
                        Action { text: operationPanel.logExpanded ? "teknik günlüğü gizle" : "teknik günlüğü göster"; implicitHeight: 34; Layout.fillWidth: true; visible: root.s.log.length > 0; onClicked: operationPanel.logExpanded = !operationPanel.logExpanded }
                        ThemeScrollView {
                            Layout.fillWidth: true; Layout.preferredHeight: 132
                            visible: operationPanel.logExpanded && root.s.log.length > 0
                            TextArea {
                                objectName: "operationLog"; text: root.s.log; readOnly: true; selectByMouse: true
                                wrapMode: TextEdit.Wrap; color: root.muted; font.pixelSize: 11
                                padding: 12; selectionColor: root.accent; selectedTextColor: root.buttonInk
                                background: Rectangle { color: root.field; radius: 8; border.color: root.line }
                                onTextChanged: cursorPosition = text.length
                            }
                        }
                        Action { text: "seçili ortamları doğrula"; Layout.fillWidth: true; enabled: root.s.operationAvailable; onClicked: controller.action("validate") }
                    }
                }
                Repeater {
                    model: root.s.components
                    Panel {
                        required property var modelData
                        ColumnLayout {
                            width: parent.width; spacing: 6
                            LabelText { text: modelData.title; font.weight: Font.DemiBold }
                            Quiet { text: modelData.detail }
                            Quiet { text: modelData.key === root.s.activeComponent && root.s.busy ? "işlem sürüyor…" : modelData.ready ? "kurulu" : modelData.present ? "kurulum tamamlanmamış · yeniden deneyebilirsin" : "kurulu değil" }
                            RowLayout {
                                Layout.fillWidth: true
                                Action { text: modelData.bundled ? "dosyaları doğrula" : modelData.ready ? "onar" : "indir"; Layout.fillWidth: true; enabled: root.s.operationAvailable; onClicked: controller.component("install",modelData.key) }
                                Action { text: "kaldır"; Layout.fillWidth: true; enabled: modelData.present && root.s.operationAvailable; onClicked: controller.component("remove",modelData.key) }
                            }
                        }
                    }
                }
                Quiet { text: "veri klasörü: " + root.s.dataPath }
            }
        }
        ThemeScrollView {
            ColumnLayout {
                width: parent.width; spacing: 14
                Panel {
                    ColumnLayout {
                        width: parent.width; spacing: 12
                        LabelText { text: "güncellemeler"; font.pixelSize: 20 }
                        Quiet { text: "yüklü sürüm: " + root.s.version }
                        Quiet { text: root.s.updates }
                        Toggle { text: "açılışta güncellemeleri kontrol et"; checked: root.s.checkUpdates; onClicked: controller.setting("check_updates",checked) }
                        Action { text: "güncellemeleri kontrol et"; Layout.fillWidth: true; enabled: root.s.operationAvailable; onClicked: controller.action("check-update") }
                        Action { text: "güncelle ve yeniden başlat"; Layout.fillWidth: true; visible: root.s.updateAvailable; enabled: root.s.operationAvailable; onClicked: controller.action("update") }
                    }
                }
                Quiet { text: "yalnızca imzalı sürüm paketleri kurulur. ayarlar ve modeller güncellemede korunur." }
                Action { text: "github · mergen"; Layout.fillWidth: true; onClicked: controller.action("github") }
                Quiet { text: "uygulamayı kaldırdığında modellerin ve ayarların korunur." }
                Action { text: "mergen uygulamasını kaldır"; Layout.fillWidth: true; enabled: root.s.canUninstall && root.s.operationAvailable; onClicked: controller.action("uninstall") }
            }
        }
    }
    footer: Rectangle {
        implicitHeight: root.s.busy ? 64 : 44
        color: root.surface
        Rectangle { width: parent.width; height: 1; color: root.line }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20; spacing: 12
            Rectangle {
                width: 6; height: 6; radius: 3; color: root.accent
                SequentialAnimation on opacity { running: root.s.busy; loops: Animation.Infinite; NumberAnimation { to: .3; duration: 600 } NumberAnimation { to: 1; duration: 600 } }
            }
            Quiet {
                id: statusLabel
                objectName: "operationStatus"
                text: root.s.busy ? root.s.phase : root.s.status
                maximumLineCount: 2; elide: Text.ElideRight
                ToolTip {
                    visible: statusHover.hovered; delay: 500
                    width: Math.min(root.width - 40, implicitWidth)
                    contentItem: Text { text: statusLabel.text; wrapMode: Text.Wrap; color: root.fg; font: root.font }
                    background: Rectangle { color: root.surface; radius: 8; border.color: root.line }
                }
                HoverHandler { id: statusHover }
            }
            Action {
                text: root.s.cancelling ? "durduruluyor…" : "vazgeç"; objectName: "cancelOperation"
                implicitHeight: 34; Layout.preferredWidth: root.s.cancelling ? 112 : 82
                visible: root.s.busy; enabled: !root.s.cancelling; onClicked: controller.action("cancel")
            }
        }
    }
}
