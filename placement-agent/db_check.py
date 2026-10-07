import asyncio
from sqlalchemy import select
from app.database.connection import get_db
from app.database.models import ExtractedData, PlacementPost

async def run_check():
    async with get_db() as session:
        # Check association mapping
        print("id | post_id | company_name")
        print("---+---------+------------------------------")
        stmt = select(ExtractedData).order_by(ExtractedData.id)
        res = await session.execute(stmt)
        extracted = res.scalars().all()
        for ext in extracted:
            print(f"{ext.id}  | {ext.post_id}       | {ext.company_name}")

        print("\n--- Detailed Investigation ---")
        for ext in extracted:
            if ext.post_id in (1, 2, 7):
                post_stmt = select(PlacementPost).where(PlacementPost.id == ext.post_id)
                post = (await session.execute(post_stmt)).scalar_one()
                print(f"\n[Post ID {ext.post_id}]")
                print(f"Title: {post.title}")
                print(f"LLM extracted company: {ext.company_name}")
                print(f"Does text contain 'DH Bars'? {'DH Bars' in post.raw_content}")
                
if __name__ == "__main__":
    asyncio.run(run_check())
