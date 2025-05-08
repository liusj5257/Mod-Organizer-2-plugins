from __future__ import annotations

import re
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Union, cast

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtWidgets import QApplication

import mobase


class ModOptionsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        options: list[tuple[str, Optional[QtGui.QPixmap], str]],
        parent: QtWidgets.QWidget | None = None,
        preselect: list[str] = None
    ):
        super().__init__(parent)
        self._selected_options: list[str] = []
        self.preview_images = {name: preview for name, preview, _ in options}
        self.modinfo_map = {name: modinfo for name, _, modinfo in options}

        self.setWindowTitle(self.tr("Select Options"))

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)

        # 左侧图片显示区域（使用QGraphicsView）
        self.graphics_view = QtWidgets.QGraphicsView()
        self.graphics_view.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.graphics_view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.graphics_view.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.graphics_view.setResizeAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.graphics_view.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.graphics_view.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.graphics_view.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.graphics_view.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.graphics_view.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.graphics_view.viewport().installEventFilter(self)

        self.scene = QtWidgets.QGraphicsScene()
        self.graphics_view.setScene(self.scene)
        self.graphics_view.setStyleSheet("border: 1px solid #444; background: #2A2A2A;")
        self.graphics_view.setMinimumSize(600, 600)
        splitter.addWidget(self.graphics_view)

        # 右侧布局
        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        # modinfo信息显示
        self.modinfo_text = QtWidgets.QTextEdit()
        self.modinfo_text.setReadOnly(True)
        self.modinfo_text.setStyleSheet("font-family: Consolas; font-size: 16px;")
        right_splitter.addWidget(self.modinfo_text)

        # 选项列表和按钮
        bottom_widget = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom_widget)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection  # 修改为单选模式
        )
        bottom_layout.addWidget(self.list_widget)

        # 添加带复选框的选项时设置初始勾选状态
        for name, _, _ in options:
            item = QtWidgets.QListWidgetItem(name)
            item.setFlags(
                QtCore.Qt.ItemFlag.ItemIsSelectable
                | QtCore.Qt.ItemFlag.ItemIsEnabled
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            )
            # 根据 preselect 设置初始勾选状态
            initial_state = QtCore.Qt.CheckState.Checked if name in preselect else QtCore.Qt.CheckState.Unchecked
            item.setCheckState(initial_state)
            self.list_widget.addItem(item)

        # 按钮区域
        button_layout = QtWidgets.QHBoxLayout()
        self.select_all_btn = QtWidgets.QPushButton(self.tr("Select All"))
        self.select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(self.select_all_btn)

        self.deselect_btn = QtWidgets.QPushButton(self.tr("Deselect All"))
        self.deselect_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(self.deselect_btn)

        self.ok_btn = QtWidgets.QPushButton(self.tr("OK"))
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_btn)

        self.cancel_btn = QtWidgets.QPushButton(self.tr("Cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        bottom_layout.addLayout(button_layout)
        right_splitter.addWidget(bottom_widget)

        splitter.addWidget(right_splitter)
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(splitter)

        # 默认选中第一个并显示信息
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            self.update_preview(self.list_widget.item(0))

        # 连接点击事件
        # self.list_widget.itemClicked.connect(self.update_preview)
        self.list_widget.itemSelectionChanged.connect(self.update_preview)

    def eventFilter(self, source, event):
        """拦截滚轮事件处理缩放"""
        if (
            source is self.graphics_view.viewport()
            and event.type() == QtCore.QEvent.Type.Wheel
        ):
            self.handle_wheel_zoom(event)
            return True  # 阻止事件继续传递
        return super().eventFilter(source, event)


    def handle_wheel_zoom(self, event: QtGui.QWheelEvent):
        current_scale = self.graphics_view.transform().m11()
        zoom_factor = 1.001 ** event.angleDelta().y()
        new_scale = current_scale * zoom_factor

        if 0.01 <= new_scale <= 50:
            # 在缩放前保存当前可视区域中心
            old_center = self.graphics_view.mapToScene(
                self.graphics_view.viewport().rect().center()
            )

            # 执行缩放
            self.graphics_view.scale(zoom_factor, zoom_factor)

            # 计算图片是否小于视图
            view_rect = self.graphics_view.mapToScene(
                self.graphics_view.viewport().rect()
            ).boundingRect()
            image_rect = self.scene.itemsBoundingRect()

            # 如果图片完全在可视区域内则自动居中
            if view_rect.contains(image_rect):
                self.graphics_view.centerOn(image_rect.center())

    def select_all(self):
        """全选复选框"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(QtCore.Qt.CheckState.Checked)

    def deselect_all(self):
        """取消全选复选框"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)

    def update_preview(self, item: Optional[QtWidgets.QListWidgetItem] = None):
        """更新预览图和modinfo信息"""
        if item is None:
            selected_items = self.list_widget.selectedItems()
            if not selected_items:
                return
            item = selected_items[0]

        name = item.text()

        # 清空原有场景
        self.scene.clear()

        # 更新预览图
        preview = self.preview_images.get(name)
        if preview:
            # 创建可缩放的图形项
            pixmap_item = QtWidgets.QGraphicsPixmapItem(preview)
            self.scene.addItem(pixmap_item)

            # 将图片居中
            pixmap_item.setTransformationMode(QtCore.Qt.TransformationMode.SmoothTransformation)
            pixmap_item.setPos(
                -preview.width() / 2, -preview.height() / 2
            )  # 设置图片中心为场景中心

            # 自动适应视图大小
            self.graphics_view.fitInView(pixmap_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        else:
            # 显示文本提示
            text_item = self.scene.addText("无可用预览")
            text_item.setDefaultTextColor(QtGui.QColor("#FFFFFF"))
            # 将文本居中
            text_item.setPos(
                -text_item.boundingRect().width() / 2,
                -text_item.boundingRect().height() / 2,
            )

        # 更新modinfo信息（保持原有逻辑）
        self.modinfo_text.setPlainText(self.modinfo_map.get(name, "无modinfo信息"))

    def resizeEvent(self, event: QtGui.QResizeEvent):
        """窗口大小变化时自动调整视图"""
        super().resizeEvent(event)
        if self.scene.items():
            self.graphics_view.fitInView(self.scene.itemsBoundingRect(),
                                       QtCore.Qt.AspectRatioMode.KeepAspectRatio)
    def selected_options(self) -> list[str]:
        """获取勾选的选项"""
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                selected.append(item.text())
        return selected
    def tr(self, value: str) -> str:
        # we need this to translate string in Python. Check the common documentation
        # for more details
        return QApplication.translate("ModOptionsDialog", value)


class MhwsInstaller(mobase.IPluginInstallerSimple):

    # regex used to parse settings
    RE_DESCRIPTION = re.compile(r"select([0-9]+)-description")
    RE_OPTION = re.compile(r"select([0-9]+)-option([0-9]+)")

    _organizer: mobase.IOrganizer

    # list of selected options
    _installerOptions: Dict[str, List[str]]
    _installerUsed: bool

    def __init__(self):
        super().__init__()
        self._init_logger()
        self.current_mod = None
        self.new_mod = None
        self._pending_selected_options = None

    def _init_logger(self) -> None:
        """初始化日志记录器"""
        self._logger = logging.getLogger("LootPaks")
        self._logger.setLevel(logging.DEBUG)

    def init(self, organizer: mobase.IOrganizer):
        self._organizer = organizer
        translator = QtCore.QTranslator()
        translator.load("MhwsInstaller_zh_CN.qm")

        return True

    def name(self):
        return "MHWS Installer"

    def localizedName(self) -> str:
        return self.tr("MHWS Installer")

    def author(self):
        return "aqeqqq"

    def description(self):
        return self.tr("MHWS")

    def version(self):
        return mobase.VersionInfo(1, 0, 0)

    def isActive(self):
        return self._organizer.pluginSetting(self.name(), "enabled")

    def settings(self):
        return [
            mobase.PluginSetting("enabled", "check to enable this plugin", True),
        ]

    # method for IPluginInstallerSimple

    def priority(self) -> int:
        return 999

    def isManualInstaller(self) -> bool:
        return False

    def onInstallationStart(
        self,
        archive: str,
        reinstallation: bool,
        current_mod: Optional[mobase.IModInterface],
    ):
        self._installerUsed = False
        self._installerOptions = {}
        self.current_mod = current_mod

    def onInstallationEnd(
        self, result: mobase.InstallResult, new_mod: Optional[mobase.IModInterface]
    ):
        self.new_mod = new_mod
        # === 新增配置保存逻辑 ===
        if (
            result == mobase.InstallResult.SUCCESS
            and self._pending_selected_options is not None
            and self.new_mod is not None
        ):
            self.new_mod.setPluginSetting(
                self.name(),
                "selected_options",
                self._pending_selected_options
            )
            self._logger.debug(f"配置已保存到 {self.new_mod.name()}: {self._pending_selected_options}")
            self._pending_selected_options = None  # 清空临时存储
        if (
            result != mobase.InstallResult.SUCCESS
            or not self._installerUsed
            or not new_mod
        ):
            return

        new_mod.clearPluginSettings(self.name())
        for i, desc in enumerate(self._installerOptions):
            new_mod.setPluginSetting(self.name(), f"select{i}-description", desc)
            for iopt, opt in enumerate(self._installerOptions[desc]):
                new_mod.setPluginSetting(self.name(), f"select{i}-option{iopt}", opt)

    def _hasFomodInstaller(self) -> bool:
        # do not consider the NCC installer
        return self._organizer.isPluginEnabled("Fomod Installer")

    def _hasOmodInstaller(self) -> bool:
        return self._organizer.isPluginEnabled("Omod Installer")

    def _getWizardArchiveBase(
        self, tree: mobase.IFileTree, data_name: str, checker: mobase.ModDataChecker
    ) -> Union[
        tuple[mobase.IFileTree, Optional[QtGui.QPixmap], dict],
        List[tuple[mobase.IFileTree, Optional[QtGui.QPixmap], dict]],
        None
    ]:

        def read_modinfo(entry: mobase.IFileTree) -> dict:
            """读取modinfo.ini内容并返回属性字典"""
            modinfo_entry = entry.find("modinfo.ini", mobase.FileTreeEntry.FILE)
            if modinfo_entry:
                try:
                    paths = self._manager().extractFile(modinfo_entry, silent=True)
                    properties = {}
                    with open(paths, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and '=' in line:
                                key, value = line.split('=', 1)
                                key = key.strip().lower()  # 统一小写处理键
                                value = value.strip()
                                properties[key] = value
                    return properties
                except Exception as e:
                    self._logger.error(f"读取modinfo.ini失败: {str(e)}")
            return {}

        def find_preview(current_tree: mobase.IFileTree) -> Optional[QtGui.QPixmap]:
            for entry in current_tree:
                if entry.isFile() and entry.suffix().lower() in ["jpg", "jpeg", "png"]:
                    try:
                        paths = self._manager().extractFile(entry, silent=False)
                        self._logger.debug(f"找到备用预览图: {paths}")
                        data= open(paths, 'rb').read()
                        if not data:
                            continue
                        pixmap = QtGui.QPixmap()
                        if pixmap.loadFromData(data):
                            self._logger.debug(f"找到备用预览图: {entry.name()}")
                            return pixmap
                    except Exception as e:
                        self._logger.error(f"加载备用预览图失败 {entry.name()}: {str(e)}")
            return None

        # 1. 检查当前层级是否直接包含 modinfo.ini
        entry = tree.find("modinfo.ini", mobase.FileTreeEntry.FILE)
        if entry:
            self._logger.debug(
                "Found modinfo.ini at the root level. Single-option mod detected."
            )
            preview = find_preview(tree)
            modinfo_text = read_modinfo(tree)
            return (tree, preview, modinfo_text)

        # 2. 如果当前层级只包含一个文件夹，进入该文件夹继续检查
        if len(tree) == 1 and isinstance((root := tree[0]), mobase.IFileTree):
            self._logger.debug("Only one folder found, entering the folder.")
            return self._getWizardArchiveBase(root, data_name, checker)

        # 3. 多选模式处理
        option_trees = []
        for entry in tree:
            if entry.isDir():
                modinfo_entry = entry.find("modinfo.ini", mobase.FileTreeEntry.FILE)
                if modinfo_entry:
                    preview = find_preview(entry)
                    modinfo_text = read_modinfo(entry)
                    option_trees.append((entry, preview, modinfo_text))

        return option_trees if option_trees else None

        self._logger.debug("No valid modinfo.ini found.")
        return None

    # def _getFluffyModArchiveBase
    def isArchiveSupported(self, tree: mobase.IFileTree) -> bool:
        """
        Check if the given file-tree (from the archive) can be installed by this
        installer.

        Args:
            tree: The tree to check.

        Returns:
            True if the file-tree can be installed, false otherwise.
        """

        # retrieve the name of the "data" folder
        data_name = self._organizer.managedGame().dataDirectory().dirName()

        # retrieve the mod-data-checker
        checker = self._organizer.gameFeatures().gameFeature(mobase.ModDataChecker)

        # retrieve the base
        base = self._getWizardArchiveBase(tree, data_name, checker)
        # self._logger.error(f"{tree} + {data_name} + {checker} + {base}")
        # tree_structure = self._log_tree_structure(tree)
        # self._logger.error(f"File tree structure:\n{tree_structure}")

        if not base:
            return False
        return True

    def install(
        self,
        name: mobase.GuessedString,
        tree: mobase.IFileTree,
        version: str,
        nexus_id: int,
    ) -> Union[mobase.InstallResult, mobase.IFileTree]:
        self._logger.debug("Start install")

        # 通过名称查找已安装MOD
        mod_name = str(name)
        self._logger.debug(mod_name)
        existing_mod = self._organizer.modList().getMod(mod_name)

        if not self.current_mod and existing_mod:
            self.current_mod = existing_mod
            self._logger.debug(f"通过名称匹配到已安装MOD: {mod_name}")

        data_name = self._organizer.managedGame().dataDirectory().dirName()
        checker = self._organizer.gameFeatures().gameFeature(mobase.ModDataChecker)
        base = self._getWizardArchiveBase(tree, data_name, checker)

        if not base:
            return mobase.InstallResult.NOT_ATTEMPTED

        # 处理单选项
        if isinstance(base, tuple):
            mod_tree, preview, modinfo = base
            new_tree = tree.createOrphanTree()
            new_tree.merge(mod_tree)
            # 清理根目录文件
            for entry in list(new_tree):
                if entry.isFile() and entry.suffix().lower() in {"ini", "jpg", "png"}:
                    new_tree.remove(entry.name())
            return new_tree

        # 处理多选项
        if isinstance(base, list):
            options_data = []
            # === 新增调试日志 ===
            self._logger.debug(f"当前MOD实例: {self.current_mod}")
            if self.current_mod:
                raw_selected = self.current_mod.pluginSetting(self.name(), "selected_options")
                self._logger.debug(f"原始读取值: {raw_selected} (类型: {type(raw_selected)})")
                previous_selected = raw_selected or []
                self._logger.debug(f"解析后的历史选中项: {previous_selected}")
            else:
                previous_selected = []
                self._logger.debug("无已安装MOD，不加载历史配置")
            # ====================

            for entry, preview, modinfo in base:
                display_name = modinfo.get('name', entry.name())
                options_data.append({
                    'display_name': display_name,
                    'preview': preview,
                    'modinfo': modinfo,
                    'entry': entry
                })
            # === 新增：记录所有可用选项 ===
            all_options = [x['display_name'] for x in options_data]
            self._logger.debug(f"可用选项列表: {all_options}")
            # ========================
            # 按name属性排序
            options_data.sort(key=lambda x: x['display_name'].lower())

            # === 新增：验证历史配置有效性 ===
            valid_selected = [name for name in previous_selected if name in all_options]
            invalid_selected = list(set(previous_selected) - set(valid_selected))
            if invalid_selected:
                self._logger.warning(f"发现无效历史选项: {invalid_selected}")
            # ========================
            # 生成对话框选项（名称、预览、处理后的描述文本）
            options_with_info = []
            for data in options_data:
                description = data['modinfo'].get('description', '无描述信息')
                description = description.replace('\\n', '\n')  # 转换\n为实际换行
                options_with_info.append((
                    data['display_name'],
                    data['preview'],
                    description
                ))

            # 创建对话框时传递预设选中的选项名列表
            self._logger.debug(f"传递给对话框的预设选项: {valid_selected}")
            dialog = ModOptionsDialog(
                options_with_info,
                self._parentWidget(),
                preselect=valid_selected  # 使用校验后的有效选项
            )

            if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                selected_names = dialog.selected_options()
                self._pending_selected_options = selected_names  # 临时保存
                self._logger.debug(f"暂存用户选择: {selected_names}")
            else:
                return mobase.InstallResult.CANCELED

            selected_names = dialog.selected_options()
            new_tree = tree.createOrphanTree()

            # 合并选中的entry
            for name in selected_names:
                for data in options_data:
                    if data['display_name'] == name:
                        new_tree.merge(data['entry'])
                        break

            # 清理根目录文件
            for entry in list(new_tree):
                if entry.isFile() and entry.suffix().lower() in {"ini", "jpg", "png"}:
                    new_tree.remove(entry.name())

            return new_tree

        return mobase.InstallResult.NOT_ATTEMPTED

    def tr(self, value: str) -> str:
        # we need this to translate string in Python. Check the common documentation
        # for more details
        return QApplication.translate("MhwsInstaller", value)


def createPlugin() -> MhwsInstaller:
    return MhwsInstaller()
