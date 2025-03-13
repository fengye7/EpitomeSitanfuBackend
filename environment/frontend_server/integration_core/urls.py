from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter

from integration_core.views import ExperimentDeleteView, ExperimentListView, ExperimentParentCheckView, PhaserGameEmbedView, VideoHLSView, ExperimentCreateView, ExperimentDetailView, ExperimentStartView, ExperimentStatusView,ExperimentStopView # 引入 ExperimentListView 视图集

urlpatterns = [    
    path('experiment_list/', ExperimentListView.as_view(),  name='experiment_list'),
    path('phaserVideo/',PhaserGameEmbedView.as_view(),name='phaserVideo'),
    path('hlsVideo/',VideoHLSView.as_view(), name='hlsVideo'),
    path('experimentCreate/',ExperimentCreateView.as_view(),name='experiment_create'),
    path('experimentStart/',ExperimentStartView.as_view(),name='experiment_start'),
    path('experimentStatus/',ExperimentStatusView.as_view(),name='experiment_status'),
    path('experimentDetail/',ExperimentDetailView.as_view(),name='experiment_detail'),
    path('experimentStop/',ExperimentStopView.as_view(),name='experiment_stop'),
    path('experimentDelete/',ExperimentDeleteView.as_view(),name='experiment_delete'),
    path('experiment_parent_check/',ExperimentParentCheckView.as_view(),name='experiment_parent_check'),
]

from .consumers import ExperimentConsumer
websocket_urlpatterns = [
    re_path(r'ws/experiment/(?P<sim_code>[^/]+)/$', ExperimentConsumer.as_asgi()),  # 使用正则表达式捕获 sim_code
]