from PIL import Image, ImageDraw, ImageFont
import os
import logging

logger = logging.getLogger("jarvis.image_generator")

def generate_vacancy_cover(position: str, company: str, salary: str, output_path: str) -> bool:
    """
    Generates a high-quality 1200x675 cover image for a vacancy.
    """
    try:
        # Create base image with dark background
        width, height = 1200, 675
        img = Image.new("RGBA", (width, height), (11, 15, 25, 255)) # Dark navy base
        draw = ImageDraw.Draw(img)

        # Draw a beautiful subtle background gradient (diagonal)
        for i in range(width):
            # Gradient color interpolation from (11, 15, 25) to (30, 41, 59)
            r = int(11 + (i / width) * 19)
            g = int(15 + (i / width) * 26)
            b = int(25 + (i / width) * 34)
            for j in range(height):
                draw.point((i, j), fill=(r, g, b, 255))

        # Add a sleek border or framing lines
        # Draw glowing neon accent line at the left edge (thickness: 8px)
        # Left border: neon blue to cyan gradient
        for y in range(height):
            g_cyan = int(189 + (y / height) * 66)  # From 189 to 255
            draw.line([(0, y), (8, y)], fill=(56, g_cyan, 248, 255))

        # Load fonts (fallback to default if not found)
        font_dir = os.path.dirname(os.path.abspath(__file__))
        bold_font_path = os.path.join(font_dir, "Inter-Bold.ttf")
        reg_font_path = os.path.join(font_dir, "Inter-Regular.ttf")

        if os.path.exists(bold_font_path):
            font_header = ImageFont.truetype(bold_font_path, 32)
            font_title = ImageFont.truetype(bold_font_path, 56)
            font_meta = ImageFont.truetype(reg_font_path, 36)
            font_meta_bold = ImageFont.truetype(bold_font_path, 36)
            font_footer = ImageFont.truetype(reg_font_path, 24)
        else:
            logger.warning("Inter fonts not found, falling back to default.")
            font_header = font_title = font_meta = font_meta_bold = font_footer = ImageFont.load_default()

        # 1. Draw Header
        draw.text((80, 70), "NUVI JOBS", fill=(56, 189, 248, 255), font=font_header) # Neon blue
        # Subtle horizontal accent line next to the header
        draw.line([(280, 88), (400, 88)], fill=(56, 189, 248, 100), width=3)

        # 2. Draw Job Title (with auto-wrap)
        position_upper = position.upper()
        max_title_width = 1000
        words = position_upper.split()
        lines = []
        current_line = []
        for word in words:
            test_line = " ".join(current_line + [word])
            # Use getbbox to measure text width in Pillow 10+
            bbox = draw.textbbox((0, 0), test_line, font=font_title)
            w = bbox[2] - bbox[0]
            if w <= max_title_width:
                current_line.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))

        # Draw lines of title
        y_text = 200
        for line in lines[:2]: # Limit to max 2 lines to avoid overlap
            draw.text((80, y_text), line, fill=(255, 255, 255, 255), font=font_title)
            bbox = draw.textbbox((0, 0), line, font=font_title)
            h = bbox[3] - bbox[1]
            y_text += h + 15

        # 3. Draw Metadata (Company & Salary)
        y_meta = 420
        # Draw Company label & value
        company_text = f"🏢  {company}"
        draw.text((80, y_meta), company_text, fill=(226, 232, 240, 255), font=font_meta)
        
        # Draw Salary label & value below it
        salary_text = f"💰  Maosh: {salary}"
        draw.text((80, y_meta + 65), salary_text, fill=(52, 211, 153, 255), font=font_meta_bold) # Green color for salary

        # 4. Draw Footer
        draw.text((80, 580), "t.me/nuvi_jobs", fill=(148, 163, 184, 255), font=font_footer)

        # Save image
        img.save(output_path, "PNG")
        logger.info(f"✅ Vacancy cover image saved successfully at: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to generate vacancy cover image: {e}")
        return False
