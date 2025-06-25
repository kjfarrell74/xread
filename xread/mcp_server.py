"""MCP Server implementation for XReader."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Sequence, Optional, Dict, List
from urllib.parse import urlparse

from mcp.server import Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    CallToolResult, ReadResourceResult, ListResourcesResult, ListToolsResult
)
import mcp.server.stdio

from xread.data_manager import AsyncDataManager
from xread.pipeline import ScraperPipeline
from xread.settings import settings, logger
from xread.models import ScrapedData, Post # Ensure Post is imported if you're reconstructing objects here
from xread.exceptions import XReaderError, NetworkError, ParseError, DatabaseError


class XReaderMCPServer:
    """MCP Server implementation for XReader functionality."""
    
    def __init__(self):
        self.server = Server("xreader")
        self.data_manager: Optional[AsyncDataManager] = None
        self.pipeline: Optional[ScraperPipeline] = None
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up MCP protocol handlers."""
        
        @self.server.list_tools()
        async def handle_list_tools():
            """List available tools."""
            tools = [
                    Tool(
                        name="scrape_url",
                        description="Scrape content from a social media URL (Twitter/Nitter, Mastodon)",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "url": {
                                    "type": "string",
                                    "description": "The URL to scrape (e.g., Twitter/Nitter post, Mastodon status)"
                                },
                                "include_replies": {
                                    "type": "boolean",
                                    "description": "Whether to include replies in the scraped data",
                                    "default": True
                                },
                                "generate_ai_report": {
                                    "type": "boolean", 
                                    "description": "Whether to generate an AI analysis report",
                                    "default": True
                                }
                            },
                            "required": ["url"]
                        }
                    ),
                    Tool(
                        name="search_posts",
                        description="Search through previously scraped posts by content or author. Returns brief summaries.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query to find posts by content or keywords. This field is mandatory."
                                },
                                "author": {
                                    "type": "string",
                                    "description": "Optional: Filter by specific author username (e.g., 'elonmusk')"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of results to return",
                                    "default": 10,
                                    "minimum": 1,
                                    "maximum": 50
                                },
                                "include_ai_reports": {
                                    "type": "boolean",
                                    "description": "Whether to include AI analysis reports in results previews",
                                    "default": False
                                }
                            },
                            "required": ["query"]
                        }
                    ),
                    Tool(
                        name="get_post",
                        description="Get detailed information about a specific post by its unique status ID. This includes full content, images, replies, and the AI report.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "post_id": {
                                    "type": "string",
                                    "description": "The unique status ID of the post to retrieve (e.g., '1777777777777777777')"
                                },
                                "include_replies": {
                                    "type": "boolean",
                                    "description": "Whether to include all replies for this post",
                                    "default": True
                                },
                                "include_ai_report": {
                                    "type": "boolean",
                                    "description": "Whether to include the full AI analysis report",
                                    "default": True
                                }
                            },
                            "required": ["post_id"]
                        }
                    ),
                    Tool(
                        name="list_recent_posts",
                        description="List recently scraped posts. Provides a quick overview of the latest content.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of recent posts to return",
                                    "default": 10,
                                    "minimum": 1,
                                    "maximum": 50
                                },
                                "include_ai_reports": {
                                    "type": "boolean",
                                    "description": "Whether to include AI analysis reports in results previews",
                                    "default": False
                                }
                            }
                        }
                    ),
                    Tool(
                        name="add_author_note",
                        description="Add or update a personal note about a specific author. These notes will be included in future scrapes involving that author.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "username": {
                                    "type": "string",
                                    "description": "The author's username (e.g., 'jack')"
                                },
                                "note": {
                                    "type": "string",
                                    "description": "The content of the note to add or update for this author"
                                }
                            },
                            "required": ["username", "note"]
                        }
                    )
                ]
            return tools
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]):
            """Handle tool calls."""
            try:
                if not self.data_manager:
                    await self._initialize_components()
                
                if name == "scrape_url":
                    result = await self._scrape_url_tool(arguments)
                    logger.info(f"DEBUG: scrape_url_tool returned type: {type(result)}")
                    logger.info(f"DEBUG: scrape_url_tool returned: {result}")
                    # Try returning the result directly without any modifications
                    return result
                elif name == "search_posts":
                    result = await self._search_posts_tool(arguments)
                    return result
                elif name == "get_post":
                    result = await self._get_post_tool(arguments)
                    return result
                elif name == "list_recent_posts":
                    result = await self._list_recent_posts_tool(arguments)
                    return result
                elif name == "add_author_note":
                    result = await self._add_author_note_tool(arguments)
                    return result
                else:
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                        isError=True
                    )
            except Exception as e:
                logger.exception(f"Error in tool call {name}: {e}")
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Error executing {name}: {str(e)}")],
                    isError=True
                )
        
        @self.server.list_resources()
        async def handle_list_resources():
            """List available resources (recently scraped posts)."""
            if not self.data_manager:
                await self._initialize_components()
            
            try:
                # Use the new get_recent_posts method from data_manager
                recent_posts = await self.data_manager.get_recent_posts(limit=50, include_ai_reports=False)
                resources = []
                
                for post_data in recent_posts:
                    status_id = post_data.get('status_id', 'unknown')
                    author = post_data.get('username', 'unknown')
                    text_preview = post_data.get('text', '')
                    text_preview = (text_preview[:100] + '...') if len(text_preview) > 100 else text_preview
                    
                    resources.append(Resource(
                        uri=f"xreader://post/{status_id}",
                        name=f"Post by @{author}: {text_preview}",
                        description=f"Scraped post {status_id} by @{author} on {post_data.get('date', 'unknown_date')}",
                        mimeType="application/json"
                    ))
                
                return resources
            except Exception as e:
                logger.error(f"Error listing resources: {e}")
                return []
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> ReadResourceResult:
            """Get a specific resource."""
            if not self.data_manager:
                await self._initialize_components()
            
            try:
                # Parse URI: xreader://post/{post_id}
                if uri.startswith("xreader://post/"):
                    post_id = uri.replace("xreader://post/", "")
                    # Use the new get_full_post_data method from data_manager
                    post_data = await self.data_manager.get_full_post_data(post_id)
                    
                    if post_data:
                        return ReadResourceResult(
                            contents=[
                                TextContent(
                                    type="text",
                                    text=json.dumps(post_data, indent=2, ensure_ascii=False)
                                )
                            ]
                        )
                    else:
                        return ReadResourceResult(
                            contents=[
                                TextContent(
                                    type="text",
                                    text=f"Post {post_id} not found"
                                )
                            ]
                        )
                else:
                    return ReadResourceResult(
                        contents=[
                            TextContent(
                                type="text",
                                text=f"Unknown resource URI: {uri}"
                            )
                        ]
                    )
            except Exception as e:
                logger.exception(f"Error getting resource {uri}: {e}")
                return ReadResourceResult(
                    contents=[
                        TextContent(
                            type="text",
                            text=f"Error getting resource: {str(e)}"
                        )
                    ]
                )
    
    async def _initialize_components(self):
        """Initialize XReader components."""
        if not self.data_manager:
            self.data_manager = AsyncDataManager()
            await self.data_manager.initialize()
        
        if not self.pipeline:
            self.pipeline = ScraperPipeline(self.data_manager)
    
    async def _scrape_url_tool(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle the scrape_url tool."""
        url = arguments.get("url")
        include_replies = arguments.get("include_replies", True)
        generate_ai_report = arguments.get("generate_ai_report", True)
        
        if not url:
            text_content = TextContent(type="text", text="URL is required")
            logger.info(f"DEBUG: TextContent created: {text_content}, type: {type(text_content)}")
            result = CallToolResult(
                content=[text_content],
                isError=True
            )
            logger.info(f"DEBUG: CallToolResult created: {result}, type: {type(result)}")
            return result
        
        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return CallToolResult(
                    content=[TextContent(type="text", text="Invalid URL format")],
                    isError=True
                )
            
            # Run the scraping pipeline (it saves to database and returns None)
            await self.pipeline.run(url)
            
            # Extract status ID from URL to retrieve the saved post
            import re
            sid_match = re.search(r'status/(\d+)', url)
            if sid_match:
                status_id = sid_match.group(1)
                post_data = await self.data_manager.get_full_post_data(status_id)
                
                if post_data:
                    main_post = post_data.get('main_post', {})
                    response_text = f"Successfully scraped post {status_id}"
                    
                    # Keep it simple for now to test JSON parsing
                    response_text += f" by @{main_post.get('username', 'unknown')}"
                    
                    if include_replies and post_data.get('replies'):
                        response_text += f" with {len(post_data['replies'])} replies"
                    
                    return CallToolResult(
                        content=[TextContent(type="text", text=response_text)],
                        isError=False
                    )
            
            return CallToolResult(
                content=[TextContent(type="text", text="Successfully scraped URL and saved to database.")],
                isError=False
            )
            
        except NetworkError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Network error during scraping: {str(e)}")],
                isError=True
            )
        except ParseError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Parsing error during scraping: {str(e)}")],
                isError=True
            )
        except DatabaseError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Database error after scraping: {str(e)}")],
                isError=True
            )
        except XReaderError as e: # Catch general XReader errors
            return CallToolResult(
                content=[TextContent(type="text", text=f"XReader error during scraping: {str(e)}")],
                isError=True
            )
        except Exception as e:
            logger.exception(f"Unexpected error scraping URL {url}: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"An unexpected error occurred during scraping: {str(e)}")],
                isError=True
            )
    
    async def _search_posts_tool(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle the search_posts tool."""
        query = arguments.get("query", "")
        author = arguments.get("author")
        limit = arguments.get("limit", 10)
        include_ai_reports = arguments.get("include_ai_reports", False)
        
        try:
            # Use the new search_posts method from data_manager
            posts = await self.data_manager.search_posts(query, author, limit, include_ai_reports)
            
            if not posts:
                return CallToolResult(
                    content=[TextContent(type="text", text="No posts found matching the search criteria.")],
                    isError=False
                )
            
            response_text = f"Found {len(posts)} posts:\n\n"
            
            for i, post in enumerate(posts, 1):
                username = post.get('username', 'unknown')
                status_id = post.get('status_id', 'unknown')
                text_content = post.get('text', '')
                
                response_text += f"{i}. @{username} (ID: {status_id})\n"
                response_text += f"   Content: {text_content[:200]}{'...' if len(text_content) > 200 else ''}\n"
                
                if include_ai_reports and post.get('ai_report'):
                    ai_report_preview = post['ai_report']
                    response_text += f"   AI Analysis Preview: {ai_report_preview[:300]}{'...' if len(ai_report_preview) > 300 else ''}\n"
                
                response_text += "\n"
            
            return CallToolResult(
                content=[TextContent(type="text", text=response_text)],
                isError=False
            )
            
        except Exception as e:
            logger.exception(f"Error searching posts: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error searching posts: {str(e)}")],
                isError=True
            )
    
    async def _get_post_tool(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle the get_post tool."""
        post_id = arguments.get("post_id")
        include_replies = arguments.get("include_replies", True)
        include_ai_report = arguments.get("include_ai_report", True)
        
        if not post_id:
            return CallToolResult(
                content=[TextContent(type="text", text="Post ID is required")],
                isError=True
            )
        
        try:
            # Use the new get_full_post_data method from data_manager
            post_data = await self.data_manager.get_full_post_data(post_id)
            
            if not post_data:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Post {post_id} not found.")],
                    isError=False
                )
            
            main_post = post_data.get('main_post', {})
            response_text = f"Post Details (ID: {post_id})\n"
            response_text += "=" * 50 + "\n\n"
            response_text += f"Author: @{main_post.get('username', 'unknown')} ({main_post.get('user', 'unknown')})\n"
            response_text += f"Date: {main_post.get('date', 'unknown')}\n"
            response_text += f"Permalink: {main_post.get('permalink', 'unknown')}\n\n"
            response_text += f"Content:\n{main_post.get('text', '')}\n\n"
            
            if main_post.get('images'):
                response_text += f"Images: {len(main_post['images'])} attached\n"
                for i, img in enumerate(main_post['images'], 1):
                    response_text += f"  Image {i}: {img.get('url', 'N/A')} (Description: {img.get('description', 'No description')})\n"
                response_text += "\n"
            
            if post_data.get('factual_context'):
                response_text += f"Factual Context:\n"
                for fact in post_data['factual_context']:
                    response_text += f"- {fact}\n"
                response_text += "\n"

            if post_data.get('topic_tags'):
                response_text += f"Topic Tags: {', '.join(post_data['topic_tags'])}\n\n"

            if post_data.get('author_note'):
                response_text += f"Author Note: {post_data['author_note']}\n\n"

            if include_ai_report and post_data.get('ai_report'):
                response_text += f"AI Analysis Report:\n{post_data['ai_report']}\n\n"
            
            if include_replies and post_data.get('replies'):
                response_text += f"Replies ({len(post_data['replies'])}):\n"
                for i, reply in enumerate(post_data['replies'][:5], 1):  # Show first 5 replies
                    reply_text = reply.get('text', '')
                    response_text += f"{i}. @{reply.get('username', 'unknown')}: {reply_text[:200]}{'...' if len(reply_text) > 200 else ''}\n"
                
                if len(post_data['replies']) > 5:
                    response_text += f"... and {len(post_data['replies']) - 5} more replies. Use 'read_resource' for full JSON.\n"
            
            return CallToolResult(
                content=[TextContent(type="text", text=response_text)],
                isError=False
            )
            
        except Exception as e:
            logger.exception(f"Error getting post {post_id}: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error getting post: {str(e)}")],
                isError=True
            )
    
    async def _list_recent_posts_tool(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle the list_recent_posts tool."""
        limit = arguments.get("limit", 10) # Default to 10 as per tool schema
        include_ai_reports = arguments.get("include_ai_reports", False)
        
        try:
            # Use the new get_recent_posts method from data_manager
            posts = await self.data_manager.get_recent_posts(limit, include_ai_reports)
            
            if not posts:
                return CallToolResult(
                    content=[TextContent(type="text", text="No recent posts found.")],
                    isError=False
                )
            
            response_text = f"Recent Posts ({len(posts)} found):\n\n"
            
            for i, post in enumerate(posts, 1):
                username = post.get('username', 'unknown')
                status_id = post.get('status_id', 'unknown')
                text_content = post.get('text', '')
                ai_summary = post.get('ai_report', '')
                
                response_text += f"{i}. @{username} (ID: {status_id})\n"
                response_text += f"   Date: {post.get('date', 'unknown')}\n"
                response_text += f"   Content: {text_content[:150]}{'...' if len(text_content) > 150 else ''}\n"
                
                if include_ai_reports and ai_summary:
                    response_text += f"   AI Summary: {ai_summary[:200]}{'...' if len(ai_summary) > 200 else ''}\n"
                
                response_text += "\n"
            
            return CallToolResult(
                content=[TextContent(type="text", text=response_text)],
                isError=False
            )
            
        except Exception as e:
            logger.exception(f"Error listing recent posts: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error listing posts: {str(e)}")],
                isError=True
            )
    
    async def _add_author_note_tool(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle the add_author_note tool."""
        username = arguments.get("username")
        note = arguments.get("note")
        
        if not username or not note:
            return CallToolResult(
                content=[TextContent(type="text", text="Username and note are required")],
                isError=True
            )
        
        try:
            # Use the existing add_general_author_note method from data_manager
            success = await self.data_manager.add_general_author_note(username, note)
            if success:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Added note for @{username}: {note}")],
                    isError=False
                )
            else:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Failed to add note for @{username}. This might be due to a database issue.")],
                    isError=True
                )
            
        except Exception as e:
            logger.exception(f"Error adding author note: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error adding note: {str(e)}")],
                isError=True
            )
    
    async def run(self):
        """Run the MCP server."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )