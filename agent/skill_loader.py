"""
Skill 加载器 - 渐进式加载实现
"""

import yaml
from pathlib import Path


class SkillLoader:
    """
    渐进式 Skill 加载器：
      阶段 1：启动时仅加载 name + description（~100 tokens）
      阶段 2：匹配成功后加载完整 SKILL.md（<5000 tokens）
      阶段 3：执行时按需加载 scripts/ 或 references/
    """

    def __init__(self, skills_dir: str = "sales-analysis"):
        self.skills_dir = Path(skills_dir)
        self.skills: list[dict] = []  # 阶段 1 缓存
        self._loaded_skill: dict | None = None  # 阶段 2 缓存

    def load_summaries(self) -> list[dict]:
        """
        阶段 1：扫描 skills_dir，仅提取 SKILL.md 的 YAML 头部信息。
        用于技能路由与快速匹配。
        """
        skill_md = self.skills_dir / "SKILL.md"
        if not skill_md.exists():
            return []

        content = skill_md.read_text(encoding="utf-8")
        # 解析 YAML front matter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1])
                if meta and isinstance(meta, dict):
                    self.skills = [{
                        "name": meta.get("name", ""),
                        "description": meta.get("description", "").strip(),
                        "trigger_keywords": meta.get("trigger_keywords", []),
                    }]
        return self.skills

    def match_skill(self, user_input: str) -> dict | None:
        """根据用户输入匹配技能包，返回匹配的 skill summary"""
        input_lower = user_input.lower()
        for skill in self.skills:
            # 检查触发词
            for kw in skill.get("trigger_keywords", []):
                if kw.lower() in input_lower:
                    return skill
            # 检查 description 关键词
            for word in ["分析", "报告", "销售", "业绩"]:
                if word in input_lower and "销售" in skill.get("description", ""):
                    return skill
        return None

    def load_full_skill(self, skill_name: str) -> str | None:
        """
        阶段 2：加载完整的 SKILL.md 内容。
        仅在技能匹配成功后调用。
        """
        skill_md = self.skills_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        content = skill_md.read_text(encoding="utf-8")
        # 去掉 YAML front matter，只保留指令部分
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return content

    def load_reference(self, filename: str) -> str | None:
        """阶段 3：按需加载 references/ 中的文件"""
        ref_path = self.skills_dir / "references" / filename
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8")
        return None

    def get_script_path(self, script_name: str) -> str | None:
        """
        阶段 3：获取 scripts/ 中脚本的路径。
        
        安全性：防止路径遍历攻击，确保脚本路径在 scripts 目录内。
        """
        # 防止路径遍历攻击：拒绝包含 .. / \ 等危险字符
        if not script_name:
            return None
        
        # 检查是否包含路径遍历字符
        dangerous_chars = ["..", "/", "\\", "\x00"]
        if any(char in script_name for char in dangerous_chars):
            print(f"⚠️ 脚本名称包含非法字符：{script_name}")
            return None
        
        # 只允许 .py 文件
        if not script_name.endswith(".py"):
            print(f"⚠️ 只支持 Python 脚本（.py）：{script_name}")
            return None
        
        script_path = self.skills_dir / "scripts" / script_name
        
        # 确保解析后的路径仍在 scripts 目录内（防止符号链接攻击）
        try:
            scripts_dir = (self.skills_dir / "scripts").resolve()
            resolved_path = script_path.resolve()
            
            # 检查是否在 scripts 目录内
            if not str(resolved_path).startswith(str(scripts_dir)):
                print(f"⚠️ 脚本路径不在 scripts 目录内：{script_name}")
                return None
                
        except Exception as e:
            print(f"⚠️ 路径解析失败：{e}")
            return None
        
        if script_path.exists() and script_path.is_file():
            return str(script_path)
        return None
