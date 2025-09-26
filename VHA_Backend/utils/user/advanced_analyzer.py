import re
import json
import math
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass
import logging

@dataclass
class AnalysisResult:
    """Kết quả phân tích tài liệu"""
    question_type: str
    confidence: float
    extracted_data: Dict[str, Any]
    calculation_steps: List[str]
    final_answer: str
    reasoning: str

class AdvancedDocumentAnalyzer:
    """Phân tích tài liệu nâng cao với khả năng suy luận và tính toán"""
    
    def __init__(self):
        self.number_patterns = {
            'percentage': r'(\d+(?:\.\d+)?)\s*%',
            'currency': r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:VND|USD|đồng|dollar)',
            'number': r'(\d+(?:,\d{3})*(?:\.\d+)?)',
            'date': r'(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})',
            'duration': r'(\d+)\s*(?:ngày|tháng|năm|tuần|giờ|phút)',
            'ratio': r'(\d+):(\d+)',
            'range': r'(\d+)\s*-\s*(\d+)'
        }
        
        self.calculation_keywords = {
            'tính': ['tính', 'tính toán', 'tính ra', 'tính được'],
            'tổng': ['tổng', 'tổng cộng', 'cộng lại', 'sum'],
            'trung bình': ['trung bình', 'average', 'trung bình cộng'],
            'phần trăm': ['phần trăm', '%', 'percent'],
            'tăng': ['tăng', 'tăng thêm', 'increase'],
            'giảm': ['giảm', 'giảm đi', 'decrease'],
            'so sánh': ['so sánh', 'compare', 'khác biệt'],
            'chia': ['chia', 'divide', 'phân chia'],
            'nhân': ['nhân', 'multiply', 'nhân với']
        }
        
        self.inference_keywords = {
            'suy ra': ['suy ra', 'dẫn đến', 'kết quả là', 'therefore'],
            'nếu': ['nếu', 'if', 'trong trường hợp'],
            'thì': ['thì', 'then', 'sẽ'],
            'vì': ['vì', 'because', 'do'],
            'nên': ['nên', 'should', 'ought to'],
            'có thể': ['có thể', 'might', 'may', 'possible'],
            'chắc chắn': ['chắc chắn', 'certainly', 'definitely']
        }
        
        self.comparison_keywords = {
            'hơn': ['hơn', 'more than', 'greater than'],
            'kém': ['kém', 'less than', 'fewer than'],
            'bằng': ['bằng', 'equal to', 'same as'],
            'cao nhất': ['cao nhất', 'highest', 'maximum'],
            'thấp nhất': ['thấp nhất', 'lowest', 'minimum'],
            'tốt nhất': ['tốt nhất', 'best', 'optimal'],
            'xấu nhất': ['xấu nhất', 'worst', 'poorest']
        }
    
    def analyze_question(self, question: str, context: str) -> AnalysisResult:
        """Phân tích câu hỏi và context để xác định loại phân tích cần thiết"""
        question_lower = question.lower()
        context_lower = context.lower()
        
        question_type = self._classify_question(question_lower)
        
        extracted_data = self._extract_data_from_context(context_lower)
        
        if question_type == 'calculation':
            return self._perform_calculation(question_lower, extracted_data)
        elif question_type == 'inference':
            return self._perform_inference(question_lower, extracted_data, context_lower)
        elif question_type == 'comparison':
            return self._perform_comparison(question_lower, extracted_data)
        else:
            return self._perform_extraction(question_lower, extracted_data)
    
    def _classify_question(self, question: str) -> str:
        """Phân loại câu hỏi"""
        if any(keyword in question for keywords in self.calculation_keywords.values() for keyword in keywords):
            return 'calculation'
        elif any(keyword in question for keywords in self.inference_keywords.values() for keyword in keywords):
            return 'inference'
        elif any(keyword in question for keywords in self.comparison_keywords.values() for keyword in keywords):
            return 'comparison'
        else:
            return 'extraction'
    
    def _extract_data_from_context(self, context: str) -> Dict[str, Any]:
        """Trích xuất dữ liệu số và thông tin từ context"""
        extracted_data = {
            'numbers': [],
            'percentages': [],
            'currencies': [],
            'dates': [],
            'durations': [],
            'ratios': [],
            'ranges': [],
            'text_entities': []
        }
        
        for pattern_name, pattern in self.number_patterns.items():
            matches = re.findall(pattern, context, re.IGNORECASE)
            if pattern_name == 'ratio':
                extracted_data['ratios'].extend([(int(m[0]), int(m[1])) for m in matches])
            elif pattern_name == 'range':
                extracted_data['ranges'].extend([(int(m[0]), int(m[1])) for m in matches])
            elif pattern_name == 'currency':
                extracted_data['currencies'].extend(matches)
            elif pattern_name == 'percentage':
                extracted_data['percentages'].extend(matches)
            elif pattern_name == 'number':
                extracted_data['numbers'].extend(matches)
            elif pattern_name == 'date':
                extracted_data['dates'].extend(matches)
            elif pattern_name == 'duration':
                extracted_data['durations'].extend(matches)
        
        extracted_data['text_entities'] = self._extract_text_entities(context)
        
        return extracted_data
    
    def _extract_text_entities(self, context: str) -> List[Dict[str, str]]:
        """Trích xuất các thực thể văn bản quan trọng"""
        entities = []
        
        key_value_patterns = [
            r'(\w+)\s*[:=]\s*([^,\n]+)',
            r'(\w+)\s+là\s+([^,\n]+)',
            r'(\w+)\s+được\s+([^,\n]+)',
            r'(\w+)\s+có\s+([^,\n]+)'
        ]
        
        for pattern in key_value_patterns:
            matches = re.findall(pattern, context, re.IGNORECASE)
            for key, value in matches:
                entities.append({
                    'key': key.strip(),
                    'value': value.strip(),
                    'type': 'key_value'
                })
        
        return entities
    
    def _perform_calculation(self, question: str, data: Dict[str, Any]) -> AnalysisResult:
        """Thực hiện tính toán dựa trên dữ liệu trích xuất"""
        calculation_steps = []
        reasoning = []
        
        if any(keyword in question for keyword in self.calculation_keywords['tổng']):
            result = self._calculate_sum(data)
            calculation_steps = result['steps']
            final_answer = f"Tổng cộng: {result['value']}"
            reasoning = ["Cộng tất cả các số liệu liên quan"]
            
        elif any(keyword in question for keyword in self.calculation_keywords['trung bình']):
            result = self._calculate_average(data)
            calculation_steps = result['steps']
            final_answer = f"Trung bình: {result['value']:.2f}"
            reasoning = ["Tính trung bình cộng của các số liệu"]
            
        elif any(keyword in question for keyword in self.calculation_keywords['phần trăm']):
            result = self._calculate_percentage(data)
            calculation_steps = result['steps']
            final_answer = f"Phần trăm: {result['value']:.2f}%"
            reasoning = ["Tính phần trăm dựa trên tỷ lệ"]
            
        elif any(keyword in question for keyword in self.calculation_keywords['tăng'] + self.calculation_keywords['giảm']):
            result = self._calculate_change(data)
            calculation_steps = result['steps']
            change_type = "tăng" if any(keyword in question for keyword in self.calculation_keywords['tăng']) else "giảm"
            final_answer = f"Mức {change_type}: {result['value']:.2f}%"
            reasoning = [f"Tính mức {change_type} giữa hai giá trị"]
            
        else:
            result = self._calculate_general(question, data)
            calculation_steps = result['steps']
            final_answer = result['value']
            reasoning = ["Thực hiện tính toán dựa trên câu hỏi"]
        
        return AnalysisResult(
            question_type='calculation',
            confidence=0.8,
            extracted_data=data,
            calculation_steps=calculation_steps,
            final_answer=final_answer,
            reasoning="; ".join(reasoning)
        )
    
    def _calculate_sum(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tính tổng các số liệu"""
        numbers = []
        steps = []
        
        for num_str in data['numbers']:
            try:
                num = float(num_str.replace(',', ''))
                numbers.append(num)
                steps.append(f"Thêm {num}")
            except:
                continue
        
        for pct_str in data['percentages']:
            try:
                pct = float(pct_str.replace('%', ''))
                numbers.append(pct)
                steps.append(f"Thêm {pct}%")
            except:
                continue
        
        total = sum(numbers)
        steps.append(f"Tổng = {total}")
        
        return {'value': total, 'steps': steps}
    
    def _calculate_average(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tính trung bình"""
        numbers = []
        steps = []
        
        for num_str in data['numbers']:
            try:
                num = float(num_str.replace(',', ''))
                numbers.append(num)
                steps.append(f"Thêm {num}")
            except:
                continue
        
        if numbers:
            avg = sum(numbers) / len(numbers)
            steps.append(f"Trung bình = {sum(numbers)} / {len(numbers)} = {avg:.2f}")
            return {'value': avg, 'steps': steps}
        else:
            return {'value': 0, 'steps': ['Không có số liệu để tính']}
    
    def _calculate_percentage(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tính phần trăm"""
        steps = []
        
        if len(data['percentages']) >= 2:
            try:
                pct1 = float(data['percentages'][0].replace('%', ''))
                pct2 = float(data['percentages'][1].replace('%', ''))
                result = (pct1 / pct2) * 100
                steps = [f"Tính {pct1}% / {pct2}% * 100 = {result:.2f}%"]
                return {'value': result, 'steps': steps}
            except:
                pass
        
        numbers = []
        for num_str in data['numbers']:
            try:
                num = float(num_str.replace(',', ''))
                numbers.append(num)
            except:
                continue
        
        if len(numbers) >= 2:
            result = (numbers[0] / numbers[1]) * 100
            steps = [f"Tính {numbers[0]} / {numbers[1]} * 100 = {result:.2f}%"]
            return {'value': result, 'steps': steps}
        
        return {'value': 0, 'steps': ['Không đủ dữ liệu để tính phần trăm']}
    
    def _calculate_change(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tính mức thay đổi"""
        steps = []
        numbers = []
        
        for num_str in data['numbers']:
            try:
                num = float(num_str.replace(',', ''))
                numbers.append(num)
            except:
                continue
        
        if len(numbers) >= 2:
            old_value = numbers[0]
            new_value = numbers[1]
            change = ((new_value - old_value) / old_value) * 100
            steps = [f"Thay đổi = ({new_value} - {old_value}) / {old_value} * 100 = {change:.2f}%"]
            return {'value': change, 'steps': steps}
        
        return {'value': 0, 'steps': ['Không đủ dữ liệu để tính thay đổi']}
    
    def _calculate_general(self, question: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tính toán chung dựa trên câu hỏi"""
        steps = []
        
        if 'chia' in question or 'divide' in question:
            numbers = [float(n.replace(',', '')) for n in data['numbers'] if n.replace(',', '').replace('.', '').isdigit()]
            if len(numbers) >= 2:
                result = numbers[0] / numbers[1]
                steps = [f"Chia {numbers[0]} / {numbers[1]} = {result:.2f}"]
                return {'value': f"{result:.2f}", 'steps': steps}
        
        elif 'nhân' in question or 'multiply' in question:
            numbers = [float(n.replace(',', '')) for n in data['numbers'] if n.replace(',', '').replace('.', '').isdigit()]
            if len(numbers) >= 2:
                result = numbers[0] * numbers[1]
                steps = [f"Nhân {numbers[0]} * {numbers[1]} = {result:.2f}"]
                return {'value': f"{result:.2f}", 'steps': steps}
        
        numbers = [float(n.replace(',', '')) for n in data['numbers'] if n.replace(',', '').replace('.', '').isdigit()]
        if numbers:
            if 'cao nhất' in question or 'lớn nhất' in question:
                result = max(numbers)
                steps = [f"Số cao nhất: {result}"]
                return {'value': f"{result}", 'steps': steps}
            elif 'thấp nhất' in question or 'nhỏ nhất' in question:
                result = min(numbers)
                steps = [f"Số thấp nhất: {result}"]
                return {'value': f"{result}", 'steps': steps}
        
        return {'value': "Không thể tính toán", 'steps': ['Không đủ dữ liệu hoặc không hiểu yêu cầu']}
    
    def _perform_inference(self, question: str, data: Dict[str, Any], context: str) -> AnalysisResult:
        """Thực hiện suy luận dựa trên context"""
        reasoning = []
        conclusion = ""
        
        if 'nếu' in question and 'thì' in question:
            conclusion = self._infer_conditional(question, data, context)
            reasoning = ["Phân tích điều kiện và kết luận"]
            
        elif any(keyword in question for keyword in self.inference_keywords['suy ra']):
            conclusion = self._infer_logical(question, data, context)
            reasoning = ["Suy luận logic từ dữ liệu"]
            
        elif any(keyword in question for keyword in self.inference_keywords['có thể']):
            conclusion = self._infer_possibility(question, data, context)
            reasoning = ["Đánh giá khả năng xảy ra"]
            
        else:
            conclusion = self._infer_general(question, data, context)
            reasoning = ["Suy luận dựa trên thông tin có sẵn"]
        
        return AnalysisResult(
            question_type='inference',
            confidence=0.7,
            extracted_data=data,
            calculation_steps=[],
            final_answer=conclusion,
            reasoning="; ".join(reasoning)
        )
    
    def _infer_conditional(self, question: str, data: Dict[str, Any], context: str) -> str:
        """Suy luận điều kiện"""
        if_match = re.search(r'nếu\s+(.+?)\s+thì\s+(.+)', question, re.IGNORECASE)
        if if_match:
            condition = if_match.group(1)
            conclusion = if_match.group(2)
            
            if self._check_condition(condition, data, context):
                return f"Nếu {condition} thì {conclusion} - Điều kiện này đúng dựa trên dữ liệu."
            else:
                return f"Nếu {condition} thì {conclusion} - Điều kiện này không đúng hoặc không đủ dữ liệu."
        
        return "Không thể phân tích điều kiện"
    
    def _infer_logical(self, question: str, data: Dict[str, Any], context: str) -> str:
        """Suy luận logic"""
        logical_relations = []
        
        for entity in data['text_entities']:
            if 'cause' in entity['key'].lower() or 'effect' in entity['key'].lower():
                logical_relations.append(f"{entity['key']}: {entity['value']}")
        
        if logical_relations:
            return f"Dựa trên các mối quan hệ logic: {'; '.join(logical_relations)}"
        else:
            return "Không tìm thấy mối quan hệ logic rõ ràng"
    
    def _infer_possibility(self, question: str, data: Dict[str, Any], context: str) -> str:
        """Suy luận khả năng"""
        positive_indicators = 0
        negative_indicators = 0
        
        for entity in data['text_entities']:
            if any(word in entity['value'].lower() for word in ['có', 'được', 'thành công', 'tốt']):
                positive_indicators += 1
            elif any(word in entity['value'].lower() for word in ['không', 'khó', 'thất bại', 'xấu']):
                negative_indicators += 1
        
        if positive_indicators > negative_indicators:
            return "Có khả năng cao xảy ra dựa trên các chỉ số tích cực"
        elif negative_indicators > positive_indicators:
            return "Khả năng thấp do các chỉ số tiêu cực"
        else:
            return "Khả năng trung bình, cần thêm thông tin"
    
    def _infer_general(self, question: str, data: Dict[str, Any], context: str) -> str:
        """Suy luận chung"""
        relevant_info = []
        
        for entity in data['text_entities']:
            if any(word in question.lower() for word in entity['key'].lower().split()):
                relevant_info.append(f"{entity['key']}: {entity['value']}")
        
        if relevant_info:
            return f"Dựa trên thông tin: {'; '.join(relevant_info)}"
        else:
            return "Không đủ thông tin để suy luận"
    
    def _check_condition(self, condition: str, data: Dict[str, Any], context: str) -> bool:
        """Kiểm tra điều kiện có đúng không"""
        condition_lower = condition.lower()
        
        for num_str in data['numbers']:
            if num_str in condition_lower:
                return True
        
        for entity in data['text_entities']:
            if entity['value'].lower() in condition_lower:
                return True
        
        return False
    
    def _perform_comparison(self, question: str, data: Dict[str, Any]) -> AnalysisResult:
        """Thực hiện so sánh"""
        comparison_steps = []
        conclusion = ""
        
        numbers = [float(n.replace(',', '')) for n in data['numbers'] if n.replace(',', '').replace('.', '').isdigit()]
        
        if len(numbers) >= 2:
            if any(keyword in question for keyword in self.comparison_keywords['cao nhất']):
                max_num = max(numbers)
                comparison_steps = [f"So sánh các số: {numbers}", f"Số cao nhất: {max_num}"]
                conclusion = f"Số cao nhất là {max_num}"
                
            elif any(keyword in question for keyword in self.comparison_keywords['thấp nhất']):
                min_num = min(numbers)
                comparison_steps = [f"So sánh các số: {numbers}", f"Số thấp nhất: {min_num}"]
                conclusion = f"Số thấp nhất là {min_num}"
                
            elif any(keyword in question for keyword in self.comparison_keywords['hơn']):
                if len(numbers) >= 2:
                    diff = numbers[0] - numbers[1]
                    comparison_steps = [f"Tính chênh lệch: {numbers[0]} - {numbers[1]} = {diff}"]
                    conclusion = f"Chênh lệch: {diff}"
                    
            elif any(keyword in question for keyword in self.comparison_keywords['bằng']):
                if len(numbers) >= 2:
                    is_equal = abs(numbers[0] - numbers[1]) < 0.01
                    comparison_steps = [f"So sánh: {numbers[0]} và {numbers[1]}"]
                    conclusion = f"Hai số {'bằng nhau' if is_equal else 'không bằng nhau'}"
        
        if not conclusion:
            conclusion = "Không đủ dữ liệu để so sánh"
            comparison_steps = ["Không tìm thấy dữ liệu số để so sánh"]
        
        return AnalysisResult(
            question_type='comparison',
            confidence=0.8,
            extracted_data=data,
            calculation_steps=comparison_steps,
            final_answer=conclusion,
            reasoning="So sánh dữ liệu"
        )
    
    def _perform_extraction(self, question: str, data: Dict[str, Any]) -> AnalysisResult:
        """Trích xuất thông tin"""
        extracted_info = []
        
        for entity in data['text_entities']:
            if any(word in question.lower() for word in entity['key'].lower().split()):
                extracted_info.append(f"{entity['key']}: {entity['value']}")
        
        if any(word in question.lower() for word in ['bao nhiêu', 'số', 'lượng', 'tỷ lệ']):
            for num_str in data['numbers']:
                extracted_info.append(f"Số liệu: {num_str}")
        
            final_answer = "; ".join(extracted_info)        
        return AnalysisResult(
            question_type='extraction',
            confidence=0.9,
            extracted_data=data,
            calculation_steps=[],
            final_answer=final_answer,
            reasoning="Trích xuất thông tin từ tài liệu"
        )

def analyze_document_question(question: str, context: str) -> AnalysisResult:
    """Phân tích câu hỏi về tài liệu"""
    analyzer = AdvancedDocumentAnalyzer()
    return analyzer.analyze_question(question, context)

def format_analysis_result(result: AnalysisResult) -> str:
    """Format kết quả phân tích thành văn bản"""
    output = []
    
    output.append(f"**Loại phân tích:** {result.question_type}")
    output.append(f"**Độ tin cậy:** {result.confidence:.1%}")
    output.append(f"**Kết luận:** {result.final_answer}")
    
    if result.calculation_steps:
        output.append("**Các bước tính toán:**")
        for i, step in enumerate(result.calculation_steps, 1):
            output.append(f"  {i}. {step}")
    
    if result.reasoning:
        output.append(f"**Lý luận:** {result.reasoning}")
    
    return "\n".join(output) 