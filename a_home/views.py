from django.shortcuts import render

def home_view(request):
    return render(request, 'a_home/home.html')

def win_view(request):
    return render(request, 'a_home/wining_patern.html')