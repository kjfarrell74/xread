import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

interface ScrapedPost {
  status_id: string;
  author: string;
  text: string;
  scrape_date: string;
  ai_report?: string;
}

export const Dashboard: React.FC = () => {
  const queryClient = useQueryClient();
  const [newUrl, setNewUrl] = useState('');

  const { data: posts, isLoading } = useQuery({
    queryKey: ['posts'],
    queryFn: () => fetch('/api/posts').then(res => res.json())
  });

  const scrapeMutation = useMutation({
    mutationFn: (url: string) => 
      fetch('/api/scrape/async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      }).then(res => res.json()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] });
      setNewUrl('');
    }
  });

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900 mb-8">XReader Dashboard</h1>
        
        {/* URL Input */}
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4">Scrape New Post</h2>
          <div className="flex gap-4">
            <input
              type="url"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="Enter Twitter/X URL..."
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={() => scrapeMutation.mutate(newUrl)}
              disabled={!newUrl || scrapeMutation.isPending}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {scrapeMutation.isPending ? 'Processing...' : 'Scrape'}
            </button>
          </div>
        </div>

        {/* Posts Grid */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {posts?.map((post: ScrapedPost) => (
            <div key={post.status_id} className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm font-medium text-blue-600">@{post.author}</span>
                <span className="text-xs text-gray-500">
                  {new Date(post.scrape_date).toLocaleDateString()}
                </span>
              </div>
              <p className="text-gray-900 mb-4 line-clamp-3">{post.text}</p>
              {post.ai_report && (
                <div className="border-t pt-4">
                  <span className="text-xs font-medium text-green-600">AI Analysis Available</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
