
import cv2
import numpy as np
from PIL import Image
import os
from typing import List

class ImageStitcher:
    """
    Класс для склейки списка изображений (кадров) в одно длинное изображение.
    Использует OpenCV для поиска перекрывающихся областей.
    """
    def __init__(self, frames: List[np.ndarray]):
        """
        Инициализатор класса.
        :param frames: Список numpy-массивов, представляющих кадры.
        """
        if not frames:
            raise ValueError("Список кадров не может быть пустым.")
        self.frames = frames
        # OpenCV работает с BGR, а скриншоты обычно в RGB. Конвертируем.
        self.frames_bgr = [cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) for frame in self.frames]

    def stitch_and_save(self, output_path: str) -> str:
        """
        Запускает процесс склейки и сохраняет результат в файл.
        :param output_path: Путь для сохранения итогового изображения.
        :return: Путь к сохраненному файлу.
        """
        try:
            if len(self.frames_bgr) == 1:
                # Если всего один кадр, просто сохраняем его.
                stitched_image_bgr = self.frames_bgr[0]
            else:
                stitched_image_bgr = self._stitch_all_frames()

            if stitched_image_bgr is None:
                raise RuntimeError("Склейка не удалась, итоговое изображение пустое.")

            # Конвертируем обратно в RGB для сохранения через PIL
            stitched_image_rgb = cv2.cvtColor(stitched_image_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(stitched_image_rgb)

            # Убедимся, что директория для сохранения существует
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            pil_img.save(output_path, 'PNG', optimize=True)
            return output_path
        except Exception as e:
            print(f"Ошибка во время склейки и сохранения: {e}")
            raise

    def _stitch_all_frames(self) -> np.ndarray:
        """
        Последовательно склеивает все кадры из списка.
        """
        # Начинаем с первого кадра
        stitched_image = self.frames_bgr[0]

        for i in range(len(self.frames_bgr) - 1):
            img_top = stitched_image
            img_bottom = self.frames_bgr[i + 1]

            # Находим высоту перекрытия
            overlap_height = self._find_overlap_height(img_top, img_bottom)

            if overlap_height <= 0:
                # Если перекрытие не найдено, просто добавляем кадр целиком
                stitched_image = np.vstack((img_top, img_bottom))
                continue

            h_bottom, _, _ = img_bottom.shape
            if overlap_height >= h_bottom:
                # Новый кадр полностью содержится в предыдущем (конец прокрутки),
                # ничего добавлять не нужно.
                print("Инфо: Новый кадр полностью содержится в предыдущем. Пропуск.")
                continue

            # Обрезаем перекрывающуюся часть из нижнего изображения
            part_to_append = img_bottom[overlap_height:, :]

            # Добавляем необрезанную часть к итоговому изображению
            stitched_image = np.vstack((img_top, part_to_append))

        return stitched_image

    def _find_overlap_height(self, img_top: np.ndarray, img_bottom: np.ndarray, confidence_threshold: float = 0.8) -> int:
        """
        Находит высоту перекрывающейся области между двумя изображениями.
        :param img_top: Верхнее изображение.
        :param img_bottom: Нижнее изображение.
        :param confidence_threshold: Порог уверенности для совпадения.
        :return: Высота перекрытия в пикселях.
        """
        h_top, w_top, _ = img_top.shape
        h_bottom, w_bottom, _ = img_bottom.shape

        # Проверка на совпадение ширины
        if w_top != w_bottom:
             print("Предупреждение: Ширина изображений не совпадает. Склейка может быть некорректной.")
             min_w = min(w_top, w_bottom)
             img_top = img_top[:, :min_w]
             img_bottom = img_bottom[:, :min_w]

        # Шаблон для поиска - верхние 30% нижнего изображения
        template_height = int(h_bottom * 0.3)
        if template_height <= 5:
            return self._fallback_overlap_height(h_bottom)
        template = img_bottom[0:template_height, :]

        # Область поиска - нижние 30% верхнего изображения
        search_region_height = int(h_top * 0.3)
        if search_region_height < template_height:
             search_region_height = template_height + 10
        if search_region_height > h_top:
            search_region_height = h_top

        search_region_start_y = h_top - search_region_height
        search_region = img_top[search_region_start_y:, :]

        try:
            # Выполняем поиск шаблона
            result = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
        except cv2.error as e:
            print(f"Ошибка OpenCV при поиске шаблона: {e}. Используем запасной вариант.")
            return self._fallback_overlap_height(h_bottom)

        if max_val >= confidence_threshold:
            match_y_in_img_top = search_region_start_y + max_loc[1]
            overlap_height = h_top - match_y_in_img_top
            return overlap_height
        else:
            print(f"Предупреждение: Уверенность совпадения ({max_val:.2f}) ниже порога ({confidence_threshold}). Используем запасной вариант.")
            return self._fallback_overlap_height(h_bottom)

    def _fallback_overlap_height(self, image_height: int) -> int:
        """
        Запасной метод: возвращает фиксированный размер перекрытия (20% от высоты кадра).
        """
        return int(image_height * 0.2)
