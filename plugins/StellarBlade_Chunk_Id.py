import mobase
import os
import logging
import uuid
import struct
from typing import List, Dict
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow, QWidget, QMessageBox
from dataclasses import dataclass, field
from ctypes import c_uint8, c_uint16, c_uint32, c_uint64


@dataclass
class FGuid:
    A: c_uint32 = field(default=c_uint32(0))
    B: c_uint32 = field(default=c_uint32(0))
    C: c_uint32 = field(default=c_uint32(0))
    D: c_uint32 = field(default=c_uint32(0))


@dataclass
class Container:
    name: str
    container_id: int = 0
    old_container_id: int = 0
    package_ids: List[int] = field(default_factory=list)


class UTOCParser:
    EXPECTED_MAGIC = b"-==--==--==--==-"

    def __init__(self, logger):
        self._logger = logger
        self.reset_parser_state()
        self.container_ids = []
        self.package_ids: Dict[int, list] = {}
        self.containers: Dict[str, Container] = {}
        self.Force = False

    def reset_parser_state(self):
        """重置解析器状态，为解析新文件做准备"""
        self.header = None
        self.offset_lengths = []
        self.compressed_blocks = []
        self.directory_index = b""
        self.entry_metas = []
        self.file_size = 0
        self.container = None

    def generate_u64_id(self, ids: List[c_uint64]) -> c_uint64:
        """生成一个新的64位无符号整数ID"""
        for _ in range(10):
            candidate = uuid.uuid4().int & 0xFFFFFFFFFFFFFFFF
            if candidate not in ids:
                ids.append(c_uint64(candidate))
                # candidate=0
                return c_uint64(candidate)
        raise ValueError("无法生成唯一的64位无符号整数ID")

    def find_and_replace_bytes(self, file_path, mappingId: Dict[int, int]):
        """
        在文件中搜索指定字节序列并替换，覆盖原文件
        :param file_path: 文件路径
        """
        replacements = 0
        with open(file_path, "rb") as f:
            data = bytearray(f.read())
        for old, new in mappingId.items():
            search_bytes = old.to_bytes(8, "little")
            replace_bytes = new.to_bytes(8, "little")
            # 查找并替换所有匹配项
            offset = 0

            while offset < len(data):
                found = data.find(search_bytes, offset)
                if found == -1:
                    break
                data[found : found + len(search_bytes)] = replace_bytes
                replacements += 1
                offset = found + len(search_bytes)

            # 覆盖原文件
        if replacements > 0:
            with open(file_path, "wb") as f:
                f.write(data)
            print(f"成功替换 {replacements} 处匹配项")
        else:
            print("未找到匹配字节序列")

    def _parse_header(self, data, utoc_f) -> Dict[int, int]:
        """解析utoc文件头"""
        header_format = "<16s BBH 9I Q 4I BBH I Q I I 5Q"
        header_size = struct.calcsize(header_format)
        header_data = struct.unpack(header_format, data[:header_size])
        encryption_guid = FGuid(
            A=c_uint32(header_data[14]),
            B=c_uint32(header_data[15]),
            C=c_uint32(header_data[16]),
            D=c_uint32(header_data[17]),
        )
        self.header = {
            "magic": header_data[0],  # 16s
            "version": header_data[1],  # B
            "reserved0": header_data[2],  # B
            "reserved00": header_data[3],  # H
            "TocHeaderSize": header_data[4],  # I
            "TocEntryCount": header_data[5],
            "TocCompressedBlockEntryCount": header_data[6],
            "TocCompressedBlockEntrySize": header_data[7],
            "CompressionMethodNameCount": header_data[8],
            "CompressionMethodNameLength": header_data[9],
            "CompressionBlockSize": header_data[10],
            "DirectoryIndexSize": header_data[11],
            "PartitionCount": header_data[12],
            "FIoContainerId": header_data[13],  # Q
            "EncryptionKeyGuid": encryption_guid,  # 4I
            "ContainerFlags": header_data[18],  # B
            "Reserved1": header_data[19],  # B
            "Reserved2": header_data[20],  # Q
            "TocChunkPerfectHashSeedsCount": header_data[21],  # I
            "PartitionSize": header_data[22],  # Q
            "TocChunksWithoutPerfectHashCount": header_data[23],  # I
            "Reserved3": header_data[24],  # I
            "Reserved4": header_data[25],  # Q
            "Reserved5": header_data[26],
            "Reserved6": header_data[27],
            "Reserved7": header_data[28],
            "Reserved8": header_data[29],
        }

        # 验证魔数
        if self.header["magic"] != self.EXPECTED_MAGIC:
            raise ValueError(
                f"无效的魔数: {self.header.magic.hex()}, 期望: {self.EXPECTED_MAGIC.hex()}"
            )
        # 如果已存在，则创建id
        if self.header["FIoContainerId"] in self.container_ids or self.Force:
            newContainerId = self.generate_u64_id(self.container_ids).value
            # 写入新id
            utoc_f.seek(56)
            utoc_f.write(struct.pack("<Q", newContainerId))

            # 记录id
            self.container.old_container_id = self.header["FIoContainerId"]
            self.container.container_id = newContainerId

            return {self.header["FIoContainerId"]: newContainerId}
        else:
            self.container_ids.append(self.header["FIoContainerId"])
            self.container.container_id = self.header["FIoContainerId"]
            return None

    def _parse_package_ids(self, data):
        """解析utoc文件中的package ids"""
        PackageId_format = "<QHBB"
        PackageId_size = struct.calcsize(PackageId_format)
        for i in range(self.header["TocEntryCount"]):
            PackageId = struct.unpack(PackageId_format, data[:PackageId_size])
            ChunkId = PackageId[0]
            ChunkType = PackageId[3]
            data = data[PackageId_size:]
            self.container.package_ids.append(ChunkId)
            if ChunkId not in self.package_ids:
                self.package_ids[ChunkId] = []
            if self.container.name not in self.package_ids[ChunkId]:
                self.package_ids[ChunkId].append(self.container.name)
        return None

    def parse_utoc(self, utoc_file: str):
        """解析单个utoc文件"""
        self.reset_parser_state()
        base_name = os.path.basename(utoc_file)
        if not base_name.endswith(".utoc"):
            return None, self.package_ids

        ucas_file = utoc_file.replace(".utoc", ".ucas")
        self._logger.debug(f"开始解析文件: {base_name}")
        self.container = Container(base_name.split(".")[0])

        with open(utoc_file, "r+b") as utoc_f:
            file_data = utoc_f.read()
            self.file_size = len(file_data)

            # 解析header
            changed_container_id = self._parse_header(file_data, utoc_f)
            toc_entry_count = self.header["TocEntryCount"]
            compression_block_size = self.header["CompressionBlockSize"]

            # 处理需要修改container ID的情况
            if changed_container_id:
                found = False
                toc_entry_start = 144
                entry_size = 12

                # 搜索匹配的ID条目
                for index in range(toc_entry_count):
                    entry_pos = toc_entry_start + index * entry_size
                    id_bytes = file_data[entry_pos : entry_pos + entry_size]
                    id_val, reverse1, reverse2, idtype = struct.unpack(
                        "<QHBB", id_bytes
                    )

                    if id_val == self.container.old_container_id and idtype == 10:
                        # 更新UTOC中的container ID
                        utoc_f.seek(entry_pos)
                        utoc_f.write(struct.pack("<Q", self.container.container_id))
                        found = True
                        break

                if not found:
                    self._logger.error(f"未找到container_id {base_name}")
                    return None, self.package_ids

                # 计算数据块位置
                toc_chunk_start = toc_entry_start + toc_entry_count * entry_size
                chunk_entry_pos = toc_chunk_start + index * 10

                # 读取数据块信息
                offset_bytes = file_data[chunk_entry_pos : chunk_entry_pos + 5]
                length_bytes = file_data[chunk_entry_pos + 5 : chunk_entry_pos + 10]
                offset_val = int.from_bytes(offset_bytes, byteorder="big")
                length_val = int.from_bytes(length_bytes, byteorder="big")

                # 计算压缩块索引
                first_block_idx = offset_val // compression_block_size
                last_block_idx = (
                    offset_val + length_val + compression_block_size - 1
                ) // compression_block_size - 1

                # 获取压缩块信息
                compression_block_start = toc_chunk_start + toc_entry_count * 10
                block_entry_pos = compression_block_start + first_block_idx * 12
                block_offset = int.from_bytes(
                    file_data[block_entry_pos : block_entry_pos + 5], "little"
                )

                # 更新UCAS文件的container_id
                with open(ucas_file, "r+b") as ucas_f:
                    self._logger.debug(f"更新ucas容器ID: {self.container.container_id}")
                    ucas_f.seek(block_offset)
                    ucas_f.write(struct.pack("<Q", self.container.container_id))

            # 解析package IDs
            self._parse_package_ids(file_data[144:])

        # 处理结果返回
        if changed_container_id or self.Force:
            msg = f"{self.container.name} {self.container.old_container_id}->{self.container.container_id}"
            self._logger.debug(f"处理完成: {msg}")
            return self.container, self.package_ids

        self._logger.debug(f"无需处理: {base_name}")
        return None, self.package_ids


class StellarBlade_Chunk_Id_Patcher(mobase.IPluginTool):
    _organizer: mobase.IOrganizer
    _mainWindow: QMainWindow
    _parentWidget: QWidget

    def __init__(self):
        super().__init__()
        self._init_logger()
        self.ucas_files = []
        self.num = 0

    def _init_logger(self) -> None:
        """初始化日志记录器"""
        self._logger = logging.getLogger("StellarBlade_Chunk_Id_Patcher")
        self._logger.setLevel(logging.DEBUG)

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        return True

    def name(self) -> str:
        return "StellarBlade_Chunk_Id_Patcher"

    def author(self) -> str:
        return "aqeqqq"

    def description(self) -> str:
        return "StellarBlade_Chunk_Id_Patcher"

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.BETA)

    def isActive(self) -> bool:
        return self._organizer.pluginSetting(self.name(), "enabled") is True

    def settings(self) -> List[mobase.PluginSetting]:
        return [mobase.PluginSetting("enabled", "enable this plugin", True)]

    def displayName(self) -> str:
        return "StellarBlade_Chunk_Id_Patcher"

    def tooltip(self) -> str:
        return "."

    def icon(self) -> QIcon:
        return QIcon()

    def setParentWidget(self, widget: QWidget):
        self._parentWidget = widget

    def _get_mod_paths(self):
        """获取关键路径信息"""
        self.mod_parent = self._organizer.modsPath()
        self._IPluginGame = self._organizer.managedGame()
        if self._IPluginGame is None:
            self._logger.error("未找到托管游戏! 插件无法初始化。")
            return False
        self.game_path = self._IPluginGame.gameDirectory().path()

    def _collect_UcasFiles(self, entry: mobase.IFileTree):
        """收集所有Ucas文件"""
        for file in list(entry):
            if file.hasSuffix("utoc"):
                baseName = file.name().rsplit(".", 1)[0]
                allMods = self._organizer.modList().allModsByProfilePriority()
                for mod in reversed(allMods):
                    mod_state = self._organizer.modList().state(mod)
                    if mod_state & mobase.ModState.ACTIVE:
                        mod_dir = os.path.join(self.mod_parent, mod)
                        utoc_path = os.path.join(
                            mod_dir, "SB/Content/Paks/~mods/" + baseName + ".utoc"
                        )
                        if os.path.exists(utoc_path):
                            self.ucas_files.append(utoc_path)
        self._logger.debug(f"找到 {len(self.ucas_files)} 个 utoc")

    def deprase_utoc(self, ucas_files: list):
        """解析utoc文件"""
        parser = UTOCParser(self._logger)
        containers = {}
        for file in ucas_files:
            container, packageids = parser.parse_utoc(file)
            if container:
                containers[container.name] = container
        for k, v in containers.items():
            self.num = self.num + 1
            self._logger.info(f"{k}:{v.old_container_id}->{v.container_id}")
        for k, v in packageids.items():
            if len(v) > 1:
                self._logger.warning(f"警告！修改相同资源 packageid = {k} :\n{v}")

    def display(self):
        """主显示逻辑"""
        self._get_mod_paths()
        virtualFileTree = self._organizer.virtualFileTree()
        mods = virtualFileTree.find("/SB/Content/Paks/~mods")
        if mods is None:
            self._logger.error("在文件树中找不到mods")
            return False

        self._collect_UcasFiles(mods)
        # 解析utoc文件
        self.deprase_utoc(self.ucas_files)
        QMessageBox.information(
            self._parentWidget,
            "处理完成",
            f"总共{len(self.ucas_files)}个mod\n已处理{self.num}个ContainerId冲突mod\n注意log是否存在修改相同Packageid的mod",
        )
        self.num = 0
        self.ucas_files.clear()


def createPlugin() -> mobase.IPlugin:
    return StellarBlade_Chunk_Id_Patcher()
