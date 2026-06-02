from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import logging

logger = logging.getLogger("jarvis.image_generator")

def generate_vacancy_cover(position: str, company: str, salary: str, output_path: str) -> bool:
    """
    Generates a highly premium, minimalistic, and modern 1200x675 cover image
    for a vacancy, featuring the NUVI Jobs branding design.
    """
    try:
        width, height = 1200, 675
        # 1. Base dark navy canvas (clean premium dark UI theme)
        img = Image.new("RGBA", (width, height), (9, 11, 20, 255))
        
        # 2. Add soft, blurry glowing blue orb in the background (matches channel style)
        glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_center = (950, 337)
        glow_radius = 280
        glow_draw.ellipse(
            [glow_center[0] - glow_radius, glow_center[1] - glow_radius,
             glow_center[0] + glow_radius, glow_center[1] + glow_radius],
            fill=(0, 102, 255, 45) # Soft translucent electric blue
        )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=100))
        img = Image.alpha_composite(img, glow_layer)
        
        draw = ImageDraw.Draw(img)
        
        # 3. Dynamic Font Paths
        font_dir = os.path.dirname(os.path.abspath(__file__))
        bold_font_path = os.path.join(font_dir, "Inter-Bold.ttf")
        reg_font_path = os.path.join(font_dir, "Inter-Regular.ttf")
        
        if os.path.exists(bold_font_path) and os.path.exists(reg_font_path):
            font_logo = ImageFont.truetype(bold_font_path, 28)
            font_logo_n = ImageFont.truetype(bold_font_path, 26)
            font_title = ImageFont.truetype(bold_font_path, 52)
            font_meta_label = ImageFont.truetype(bold_font_path, 18)
            font_meta_val = ImageFont.truetype(reg_font_path, 32)
            font_meta_sal = ImageFont.truetype(bold_font_path, 36)
            font_footer = ImageFont.truetype(reg_font_path, 22)
        else:
            logger.warning("Inter fonts not found, falling back to default.")
            font_logo = font_logo_n = font_title = font_meta_label = font_meta_val = font_meta_sal = font_footer = ImageFont.load_default()
            
        # 4. Brand Logo (NUVI Jobs Circle Blue N Icon & Name)
        circle_bbox = [80, 56, 128, 104]
        draw.ellipse(circle_bbox, fill=(0, 102, 255, 255))
        draw.text((95, 62), "N", fill=(255, 255, 255, 255), font=font_logo_n)
        draw.text((144, 63), "NUVI JOBS", fill=(255, 255, 255, 255), font=font_logo)
        
        # 5. Job Title (auto-wrap up to 2 lines)
        position_upper = position.upper()
        max_title_width = 850
        words = position_upper.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font_title)
            w = bbox[2] - bbox[0]
            if w <= max_title_width:
                current_line.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))
            
        y_text = 200
        for line in lines[:2]: # Limit to 2 lines to avoid overlapping
            draw.text((80, y_text), line, fill=(255, 255, 255, 255), font=font_title)
            bbox = draw.textbbox((0, 0), line, font=font_title)
            h = bbox[3] - bbox[1]
            y_text += h + 15
            
        # Subtle glowing separator line
        divider_y = max(360, y_text + 10)
        draw.line([(80, divider_y), (350, divider_y)], fill=(0, 102, 255, 120), width=3)
        
        # 6. Metadata Columns (Company & Salary)
        y_meta = divider_y + 40
        
        # Column 1: Company
        draw.text((80, y_meta), "KOMPANIYA", fill=(113, 128, 150, 255), font=font_meta_label)
        draw.text((80, y_meta + 35), company, fill=(255, 255, 255, 255), font=font_meta_val)
        
        # Column 2: Salary (Vibrant Mint Green)
        draw.text((650, y_meta), "MAOSH / ISH HAQI", fill=(113, 128, 150, 255), font=font_meta_label)
        draw.text((650, y_meta + 35), salary, fill=(0, 230, 118, 255), font=font_meta_sal)
        
        # 7. Clean Minimalist Footer
        draw.text((80, 580), "t.me/nuvi_jobs", fill=(74, 85, 104, 255), font=font_footer)
        draw.text((900, 580), "NUVI AI Agency", fill=(74, 85, 104, 255), font=font_footer)
        
        # Convert to RGB and save as PNG
        img.convert("RGB").save(output_path, "PNG")
        logger.info(f"✅ Vacancy cover image saved successfully at: {output_path}")
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Failed to generate vacancy cover image: {e}")
        return False
