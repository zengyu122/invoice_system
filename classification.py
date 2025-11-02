#!/usr/bin/python
# -*- coding: utf-8 -*-
# @version        : 
# @Create Time    : 2025/11/2 0:12 
# @File           : classification.py
# @IDE            : PyCharm
# @desc           :
# backend/classification.py

import os
import shutil
import pdfplumber

def classify_pdfs(source_folder):
    """
    根据PDF文件内容对发票进行分类

    :param source_folder: 包含PDF文件的源文件夹路径
    :return: 分类结果的字典，键为类别，值为文件列表
    """
    categories = {
        "地铁发票": ["地铁", "城市轨道", "轨道交通", "城市轨道交通服务", "地铁集团", "三号线"],
        "高铁发票": ["铁路", "无座", "硬座", "二等座", "高铁", "动车", "火车票"],
        "滴滴打车发票": ["客运服务", "客运服务费", "滴滴", "快车", "专车", "出租车"],
        "顺丰发票": ["收派服务", "收派服务费", "快递服务", "收派", "物流", "顺丰"],
        "通行费电子发票": ["通行费", "经营租赁", "高速公路", "ETC", "停车费"],
        "餐饮发票": ["餐饮", "饭店", "餐厅", "食品", "外卖"],
        "住宿发票": ["住宿", "酒店", "宾馆", "旅馆"],
        "办公用品发票": ["办公用品", "文具", "打印", "复印", "纸张"],
        "其他发票": []  # 默认分类
    }

    temp_output = os.path.join(source_folder, "temp_output")
    if not os.path.exists(temp_output):
        os.makedirs(temp_output)

    # 创建分类子文件夹
    for category in categories.keys():
        folder_path = os.path.join(temp_output, category)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

    # 遍历源文件夹中的所有PDF文件
    for filename in os.listdir(source_folder):
        if filename.lower().endswith('.pdf'):
            filepath = os.path.join(source_folder, filename)

            try:
                # 读取PDF内容
                content = extract_text_from_pdf(filepath).lower()

                # 根据内容进行分类
                category = "其他发票"  # 默认分类
                for cat_name, keywords in categories.items():
                    if cat_name == "其他发票":
                        continue
                    if contains_any(content, keywords):
                        category = cat_name
                        break

                # 移动文件到临时分类文件夹
                new_path = os.path.join(temp_output, category, filename)
                os.rename(filepath, new_path)
                print(f"已分类: {filename} -> {category}")

            except Exception as e:
                print(f"处理文件 {filename} 时出错: {e}")
                continue

    return temp_output

def contains_any(text, keywords):
    """
    检查文本中是否包含任意关键词

    :param text: 要检查的文本
    :param keywords: 关键词列表
    :return: 是否包含任意关键词
    """
    return any(keyword.lower() in text for keyword in keywords)

def extract_text_from_pdf(pdf_path):
    """
    从PDF文件中提取文本内容

    :param pdf_path: PDF文件路径
    :return: 提取的文本内容
    """
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def move_to_output(temp_output_folder):
    """
    将分类好的文件夹从临时文件夹移动到output文件夹

    :param temp_output_folder: 临时分类文件夹路径
    """
    # 创建output文件夹
    output_folder = "output"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # 移动每个分类文件夹
    for category in os.listdir(temp_output_folder):
        src = os.path.join(temp_output_folder, category)
        dst = os.path.join(output_folder, category)

        # 如果目标文件夹已存在，合并内容
        if os.path.exists(dst):
            for filename in os.listdir(src):
                src_file = os.path.join(src, filename)
                dst_file = os.path.join(dst, filename)
                if os.path.isfile(src_file):
                    shutil.move(src_file, dst_file)
            os.rmdir(src)  # 删除空文件夹
        else:
            shutil.move(src, dst)

    # 删除临时文件夹
    os.rmdir(temp_output_folder)
    print("所有分类文件夹已成功移动到output目录")