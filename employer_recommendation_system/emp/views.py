from django.shortcuts import render,redirect
from django.contrib.auth import authenticate,login,logout
from .models import *
from emp.models import Student as RecStudent
from spoken.models import TestAttendance, FossMdlCourses,FossCategory,Profile, SpokenState, SpokenCity
from moodle.models import MdlQuizGrades
from django.views.generic.edit import UpdateView
from spoken.models import SpokenStudent 
from spoken.models import SpokenUser as SpkUser 
from django.views.generic import FormView
from emp.forms import StudentGradeFilterForm, EducationForm,StudentForm,DateInput,PrevEducationForm
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic.edit import CreateView,UpdateView,ModelFormMixin,FormMixin
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponse, JsonResponse
from .filterset import CompanyFilterSet,JobFilter
from .forms import ACTIVATION_STATUS, JobSearchForm, JobApplicationForm
import numpy as np
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.conf import settings
from django.forms import HiddenInput
from django.template.defaultfilters import slugify
from django import forms
import pandas as pd
import json
from django.core.files.storage import FileSystemStorage
from os import listdir
import re
from django.utils.datastructures import MultiValueDictKeyError

APPLIED = 0 # student has applied but not yet shortlisted by HR Manager
APPLIED_SHORTLISTED = 1 # student has applied & shortlisted by HR Manager
JOB_RATING=[(0,'Only visible to Admin/HR'),(1,'Display on homepage'),(2,'Visible to all users')]
JOB_STATUS=[(1,'Active'),(0,'Inactive')]
CURRENT_EDUCATION = 1
PAST_EDUCATION = 2

#show job application status to HR
def get_job_app_status(job):
    job_shortlist = JobShortlist.objects.filter(job=job)



def get_recommended_jobs(student):
    #get jobs having status 0 & last app submission date greater than equal to today
    jobs = Job.objects.filter(last_app_date__gte=datetime.datetime.now(),status=1)
    applied_jobs = [x.job for x in get_applied_joblist(student.spk_usr_id)]
    jobs = [x for x in jobs if x not in applied_jobs ]
    scores = fetch_student_scores(student)
    if scores:
        mdl_user_id = scores[0]['mdl'].userid
    student_foss = [d['foss'] for d in scores]  #fosses for which student grade is available
    rec_jobs = []
    spk_student = SpokenStudent.objects.get(user_id=student.spk_usr_id)
    for job in jobs:
        fosses = list(map(int,job.foss.split(',')))
        states = '' if job.state=='0' else list(map(int,job.state.split(',')))
        cities = '' if job.city=='0' else list(map(int,job.city.split(',')))
        insti_type = '' if job.institute_type=='0' else list(map(int,job.institute_type.split(',')))
        valid_fosses = [   d['foss'] for d in scores if str(d['foss']) in job.foss and int(d['grade'])>=job.grade]
        if valid_fosses:
            mdl_quiz_ids = [x.mdlquiz_id for x in FossMdlCourses.objects.filter(foss_id__in=valid_fosses)] #Student passes 1st foss & grade criteria
            test_attendance = TestAttendance.objects.filter(student=spk_student, 
                                                mdlquiz_id__in=mdl_quiz_ids,
                                                test__academic__state__in=states if states!='' else SpokenState.objects.all(),
                                                test__academic__city__in=cities if cities!='' else SpokenCity.objects.all(),
                                                status__gte=3,
                                                test__academic__institution_type__in=insti_type,
                                                test__academic__status__in=[job.activation_status] if job.activation_status else [1,3],
                                                )
            if job.from_date and job.to_date:
                test_attendance = test_attendance.filter(test__tdate__range=[job.from_date, job.to_date])
            elif job.from_date:
                test_attendance = test_attendance.filter(test__tdate__gte=job.from_date)
            if test_attendance:
                rec_jobs.append(job)
    return rec_jobs

#function to get student spoken test scores; returns list of dictionary of foss & scores
def fetch_student_scores(student):  #parameter : recommendation student obj
    scores = []
    #student = Student.objects.get(id=2) #TEMPORARY
    spk_user = student.spk_usr_id
    try:
        spk_student = SpokenStudent.objects.get(user=spk_user)
        testattendance = TestAttendance.objects.values('mdluser_id').filter(student=spk_student)
        mdl_grades = MdlQuizGrades.objects.using('moodle').filter(userid=testattendance[0]['mdluser_id']) #fetch all rows with mdl_course & grade
        for item in mdl_grades: #map above mdl_course with foss from fossmdlcourse
            try:
                foss_mdl_courses = FossMdlCourses.objects.get(mdlquiz_id=item.quiz)
                foss = foss_mdl_courses.foss
                scores.append({'foss':foss.id,'name':foss.foss,'grade':item.grade,'quiz':item.quiz,'mdl':item})
            except FossMdlCourses.DoesNotExist as e:
                print(e)
    except SpokenStudent.DoesNotExist as e:
        print(e)
    except IndexError as e:
        print(e)
    return scores


def get_applied_joblist(spk_user_id):
    return JobShortlist.objects.filter(spk_user=spk_user_id,status__in=[APPLIED,APPLIED_SHORTLISTED])

def get_awaiting_jobs(spk_user_id):  #Jobs for which the student has not yet applied
    all_jobs = Job.objects.all()
    applied_jobs = [x.job for x in get_applied_joblist(spk_user_id)]
    return list(set(all_jobs)-set(applied_jobs))

def student_homepage(request):
    context={}

    # Top 5 jobs & company to display on student homepage
    company_display = Company.objects.filter(rating=5).order_by('-date_updated')[:7]
    context['company_display']=company_display
    rec_student = Student.objects.get(user=request.user)
    applied_jobs = get_applied_joblist(rec_student.spk_usr_id)
    awaiting_jobs = get_awaiting_jobs(rec_student.spk_usr_id)
    rec_jobs = get_recommended_jobs(rec_student)
    context['applied_jobs'] = applied_jobs if len(applied_jobs)<4 else applied_jobs[:4]
    context['awaiting_jobs'] = awaiting_jobs if len(awaiting_jobs)<2 else awaiting_jobs[:2]
    l = awaiting_jobs if len(applied_jobs)<2 else awaiting_jobs[:2]
    context['APPLIED_SHORTLISTED']=APPLIED_SHORTLISTED
    context['rec_jobs'] = rec_jobs if len(applied_jobs)<3 else rec_jobs[:3]
    
    try:
         spk_student = SpokenStudent.objects.using('spk').filter(user_id=rec_student.spk_usr_id).get()
         id = spk_student.id
         test_attendance_entries = TestAttendance.objects.using('spk').filter( student_id = spk_student.id)
         for ta in test_attendance_entries :
             mdl_user_id = ta.mdluser_id
             mdl_course_id = ta.mdlcourse_id
             mdl_quiz_id = ta.mdlquiz_id
             quiz_grade = MdlQuizGrades.objects.using('moodle').filter(userid=mdl_user_id , quiz=mdl_quiz_id)
             spk_mdl_course_map = FossMdlCourses.objects.using('spk').get(mdlcourse_id=mdl_course_id)
             spk_foss = FossCategory.objects.using('spk').get(id=spk_mdl_course_map.foss_id)
    except:
        print('failed')
    scores = fetch_student_scores(rec_student)
    context['scores']=scores
    return render(request,'emp/student_homepage.html',context)

def employer_homepage(request):
    context={}
    return render(request,'emp/employer_homepage.html',context)

def manager_homepage(request):
    context={}
    return render(request,'emp/manager_homepage.html',context)

def handlelogout(request):
    logout(request)
    # return redirect('index')
    return redirect('login')

def index(request):
     context={}
     return render(request,'emp/login.html',context)
     # return render(request,'emp/index.html',context)

#Not required now
class StudentGradeFilter(FormView):
    template_name = 'emp/student_grade_filter.html'
    form_class = StudentGradeFilterForm
    success_url = '/student_grade_filter' 

    def test_func(self):
        return self.request.user.is_superuser

    def form_valid(self, form):
        if form.is_valid:
            foss = [x for x in form.cleaned_data['foss']]
            state = [s for s in form.cleaned_data['state']]
            city = [c for c in form.cleaned_data['city']]
            grade = form.cleaned_data['grade']
            activation_status = form.cleaned_data['activation_status']
            institution_type = [t for t in form.cleaned_data['institution_type']]
            from_date = form.cleaned_data['from_date']
            to_date = form.cleaned_data['to_date']
            result=self.filter_student_grades(foss, state, city, grade, institution_type, activation_status, from_date, to_date)

        else:
            pass
        return self.render_to_response(self.get_context_data(form=form, result=result))

    def filter_student_grades(self, foss=None, state=None, city=None, grade=None, institution_type=None, activation_status=None, from_date=None, to_date=None):
        if grade:
            try:
                #get the moodle id for the foss
                fossmdl=FossMdlCourses.objects.using('spk').filter(foss__in=foss)
                #get moodle user grade for a specific foss quiz id having certain grade
                user_grade=MdlQuizGrades.objects.using('moodle').values_list('userid', 'quiz', 'grade').filter(quiz__in=[f.mdlquiz_id for f in fossmdl], grade__gte=int(grade))
                #convert moodle user and grades as key value pairs
                dictgrade = {i[0]:{i[1]:[i[2],False]} for i in user_grade}
                #get all test attendance for moodle user ids and for a specific moodle quiz ids
                test_attendance=TestAttendance.objects.using('spk').filter(
                    mdluser_id__in=list(dictgrade.keys()),
                    mdlquiz_id__in=[f.mdlquiz_id for f in fossmdl],
                    test__academic__state__in=state if state else SpokenState.objects.using('spk').all(),
                    test__academic__city__in=city if city else SpokenCity.objects.using('spk').all(),
                    status__gte=3, 
                    test__academic__institution_type__in=institution_type if institution_type else InstituteType.objects.using('spk').all(), 
                    test__academic__status__in=[activation_status] if activation_status else [1,3]
                    )

                if from_date and to_date:
                    test_attendance = test_attendance.filter(test__tdate__range=[from_date, to_date])
                elif from_date:
                    test_attendance = test_attendance.filter(test__tdate__gte=from_date)
                filter_ta=[]
                filter_user_id=''
                for i in range(test_attendance.count()):
                    if not dictgrade[test_attendance[i].mdluser_id][test_attendance[i].mdlquiz_id][1]:
                        dictgrade[test_attendance[i].mdluser_id][test_attendance[i].mdlquiz_id][1] = True
                        filter_ta.append(test_attendance[i])
                        filter_user_id+=str(test_attendance[i].student.user.id) +','
               
                return {'mdl_user_grade': dictgrade, 'test_attendance': filter_ta, "count":len(filter_ta),"filter_user_id":filter_user_id[:-1]}
            except FossMdlCourses.DoesNotExist:
                return None
        return None
def get_state_city_lst():
    states = SpokenState.objects.all()
    cities = SpokenCity.objects.all()
    return states, cities
#---------------- CBV for Create, Detail, List, Update for Company starts ----------------#

class CompanyCreate(PermissionRequiredMixin,SuccessMessageMixin,CreateView):
    template_name = 'emp/employer_form.html'
    permission_required = 'emp.add_company'
    model = Company
    fields = ['name','emp_name','emp_contact','state_c','city_c','address','email','logo','description','domain','company_size','website','rating','status'] 
    success_message ="%(name)s was created successfully"
    def get_success_url(self):
        obj = Company.objects.get(name=self.object.name,date_created=self.object.date_created)
        return reverse('company-detail', kwargs={'slug': obj.slug})
    
    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.added_by = self.request.user
        self.object.save()
        messages.success(self.request, 'Company information added successfully.')
        return super(ModelFormMixin, self).form_valid(form)
    
    def test_func(self):
        return self.request.user.groups
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state,city = get_state_city_lst()
        context['state']=state
        context['city']=city
        return context
    
    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_form(self, form_class=None):
        if form_class is None:
            form_class = self.get_form_class()
        form = super(CompanyCreate, self).get_form(form_class)
        form.fields['name'].widget.attrs ={'placeholder': 'Company Name'}
        


        return form

        # return form_class(**self.get_form_kwargs())

class CompanyDetailView(PermissionRequiredMixin,DetailView):
    template_name = 'emp/employer_detail.html'
    permission_required = 'emp.view_company'
    model = Company
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_state = SpokenState.objects.get(id=self.object.state_c)
        company_city = SpokenCity.objects.get(id=self.object.city_c)
        context['company_state']=company_state.name
        context['company_city']=company_city.name
        return context

class CompanyListView(PermissionRequiredMixin,ListView):
    template_name = 'emp/employer_list.html'
    permission_required = 'emp.view_company'
    model = Company
    filterset_class = CompanyFilterSet
    # paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.collection
        context['form'] = self.collection.form
        context['companies'] = Company.objects.values_list('name')
        
        return context
    
    def get_queryset(self):
        queryset = super().get_queryset()
        self.collection = self.filterset_class(self.request.GET, queryset=queryset)
        return self.collection.qs.distinct()


class CompanyUpdate(PermissionRequiredMixin,SuccessMessageMixin,UpdateView):
    template_name = 'emp/employer_update_form.html'
    permission_required = 'emp.change_company'
    model = Company
    fields = ['name','emp_name','emp_contact','state_c','city_c','address','email','logo','description','domain','company_size','website'] 
    success_message ="%(name)s was updated successfully"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['state']=SpokenState.objects.all()
        context['city']=SpokenCity.objects.all()
        return context

    def get_form(self):
        form = super(CompanyUpdate, self).get_form()
        form.fields['state_c'].widget = HiddenInput()
        form.fields['city_c'].widget = HiddenInput()
        return form

#---------------- CBV for Create, Detail, List, Update for Jobs starts ----------------#
class JobCreate(PermissionRequiredMixin,SuccessMessageMixin,CreateView):
    template_name = 'emp/jobs_form.html'
    permission_required = 'emp.add_job'
    model = Job
    fields = ['company','title','designation','state_job','city_job','skills','description','domain','salary_range_min',
    'salary_range_max','job_type','requirements','shift_time','key_job_responsibilities','gender',
    'last_app_date','rating','foss','grade','activation_status','from_date','to_date','state','city','institute_type','status']
    success_message ="%(title)s job was created successfully"
    def get_success_url(self):
        obj = Job.objects.get(title=self.object.title,date_created=self.object.date_created)
        return reverse('job-detail', kwargs={'slug': obj.slug})
    
    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        messages.success(self.request, 'Job information added successfully.')
        return super(ModelFormMixin, self).form_valid(form)

    def get_form(self):
        form = super(JobCreate, self).get_form()
        form.fields['last_app_date'].widget = DateInput()
        form.fields['from_date'].widget = DateInput()
        form.fields['to_date'].widget = DateInput()
        form.fields['rating'].widget = forms.Select(attrs=None, choices=JOB_RATING)
        form.fields['status'].widget = forms.Select(attrs=None, choices=JOB_STATUS)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # get data for filters
        filter_form = StudentGradeFilterForm()
        state,city = get_state_city_lst()
        context['state']=state
        context['city']=city
        context['filter_form']=filter_form
        return context

class JobDetailView(DetailView):
    template_name = 'emp/jobs_detail.html'
    model = Job
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

class JobListView(FormMixin,ListView):
    template_name = 'emp/jobs_list.html'
    model = Job
    #filterset_class = JobFilter
    paginate_by = 8
    form_class = JobSearchForm
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.groups.filter(name='STUDENT'):
            jobShortlist = JobShortlist.objects.filter(spk_user=self.request.user.student.spk_usr_id)
            job_short_list = get_applied_joblist(self.request.user.student.spk_usr_id)
            all_jobs = Job.objects.all()
            applied_jobs = [x.job for x in job_short_list]
            accepted_jobs = [x.job for x in job_short_list if x.status==1]
            rejected_jobs = [x.job for x in job_short_list if x.status==0]
            reccomended_jobs = get_recommended_jobs(self.request.user.student)
            context['applied_jobs'] = applied_jobs
            context['accepted_jobs'] = accepted_jobs
            context['rejected_jobs'] = rejected_jobs
            context['reccomended_jobs'] = reccomended_jobs
            eligible_jobs = reccomended_jobs+applied_jobs
            context['non_eligible_jobs'] = list(set(all_jobs).difference(set(eligible_jobs)))
        elif self.request.user.groups.filter(name='MANAGER'):
            context['grade_filter_url'] = settings.GRADE_FILTER
        return context
    def get_queryset(self):
        queryset = super().get_queryset()
        place = self.request.GET.get('place', '')
        keyword = self.request.GET.get('keyword', '')
        company = self.request.GET.get('company', '')
        job_id = self.request.GET.get('id', '')
        if job_id:
            queryset = Job.objects.filter(id=job_id)
            return queryset
        queries =[place,keyword,company]
        if keyword or company or place:
            q_kw=q_place=q_com=Job.objects.all()
            if keyword:
                fossc = FossCategory.objects.filter(foss=keyword)
                if fossc:
                    foss_id = str(fossc[0].id)
                    l_kw = Job.objects.raw('select * from emp_job where find_in_set('+foss_id+',foss) <> 0')
                    q_kw = Job.objects.filter(id__in=[ job.id for job in l_kw])
                else:
                    q_kw = Job.objects.filter(title__icontains=keyword)
            if place:
                place = SpokenState.objects.filter(name=place) or SpokenCity.objects.filter(name=place)
                place_id = place[0].id
                q_place = Job.objects.filter(Q(state_job=place_id) | Q(city_job=place_id))
            if company:
                q_com = Job.objects.filter(company__name=company)
            queryset = (q_kw & q_place & q_com)
        return queryset

class JobListingView(ListView):
    template_name = 'emp/job_list_tabular.html'
    model = Job

class AppliedJobListView(ListView):
    template_name = 'emp/applied_jobs_list.html'
    model = JobShortlist
    # paginate_by = 2
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['APPLIED_SHORTLISTED']=APPLIED_SHORTLISTED
        context['APPLIED']=APPLIED
        return context
    def get_queryset(self):
        queryset = super().get_queryset()
        return JobShortlist.objects.filter(student=self.request.user.student)



class JobUpdate(PermissionRequiredMixin,SuccessMessageMixin,UpdateView):
    template_name = 'emp/jobs_update_form.html'
    permission_required = 'emp.change_job'
    model = Job
    fields = ['company','title','designation','state_job','city_job','skills','description','domain','salary_range_min',
    'salary_range_max','job_type','requirements','shift_time','key_job_responsibilities','gender',
    'last_app_date','rating','foss','grade','activation_status','from_date','to_date','state','city','institute_type','status']
    success_message ="%(title)s was updated successfully"


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # get data for filters
        job = Job.objects.get(id=self.kwargs['slug'])
        context['state']=SpokenState.objects.all()
        context['city']=SpokenCity.objects.all()
        context['job']=job
        context['filter_foss']=list(map(int,job.foss.split(',')))
        filter_form = StudentGradeFilterForm({'foss':job.foss,'state':job.state,
            'city':job.city,'grade':job.grade,'institution_type':job.institute_type,
            'activation_status':job.activation_status,'from_date':job.from_date,'to_date':job.to_date})
        context['filter_form']=filter_form
        return context

    filter_form = StudentGradeFilterForm()

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        messages.success(self.request, 'Job information updated successfully.')
        return super(ModelFormMixin, self).form_valid(form)


def add_education(student,degree,discipline,institute,start_year,end_year,gpa,order):
    try:
        education = Education.objects.get(student=student,order=order)
        education.degree = degree if degree else None
        education.discipline = discipline if discipline else None
        education.institute = institute if start_year else None
        education.start_year = start_year if start_year else None
        education.end_year = end_year if end_year else None
        education.gpa = gpa if end_year else None
        education.save()
        student.education.add(education)
    except:
        if degree or discipline or institute or start_year or end_year or gpa:
            education = Education(degree=degree if degree else None,
                acad_discipline=discipline if discipline else None,
                institute=institute if institute else None,
                start_year=start_year if start_year else None,
                end_year=end_year if end_year else None,
                gpa=gpa if gpa else None,
                order=order)
            education.save()
            student.education.add(education)

def save_prev_education(request,student):
    degree = request.POST.get('p_degree','')
    discipline = request.POST.get('p_discipline','')
    institute = request.POST.get('p_institute','')
    start_year = request.POST.get('p_start_year','')
    end_year = request.POST.get('p_end_year','')
    gpa = request.POST.get('p_gpa','')
    add_education(student,degree=degree,
        discipline = discipline,
        institute = institute,
        start_year = start_year, end_year = end_year,
        gpa = gpa , order=PAST_EDUCATION)


def save_education(edu_form,student):
    degree = edu_form.cleaned_data['degree']
    discipline = edu_form.cleaned_data['acad_discipline']
    institute = edu_form.cleaned_data['institute']
    start_year = edu_form.cleaned_data['start_year']
    end_year = edu_form.cleaned_data['end_year']
    gpa = edu_form.cleaned_data['gpa']
    add_education(student,degree=degree,
        discipline = discipline,
        institute = institute,
        start_year = start_year, end_year = end_year,
        gpa = gpa , order=CURRENT_EDUCATION)
    
def save_student_profile(request,student):    
    student_form = StudentForm(request.POST,request.FILES)
    c_education_form = EducationForm(request.POST)
        
    if student_form.is_valid() and c_education_form.is_valid():
        student.about = student_form.cleaned_data['about']
        student.github = student_form.cleaned_data['github']
        student.linkedin = student_form.cleaned_data['linkedin']
        student.alternate_email = student_form.cleaned_data['alternate_email']
        student.phone = student_form.cleaned_data['phone']
        student.address = student_form.cleaned_data['address']
        
        # code for saving projects starts
        urls = request.POST.getlist('pr_url', '')
        descs = request.POST.getlist('pr_desc', '')
        projects = student.projects.all()
        for project in projects:
            student.projects.remove(project)
            project.delete()
        # urls = [x for x in urls if x!='']
        # descs = [x for x in descs if x!='']
        for (url,desc) in zip(urls,descs):
            if url or desc:
                project = Project.objects.create(url = url,desc = desc)
                student.projects.add(project)
        # code for saving projects ends

        # code for saving cover letter & resume starts
        try:
            location = settings.MEDIA_ROOT+'/students/'+str(request.user.id)+'/'
            os.makedirs(location)
        except:
            pass
        fs = FileSystemStorage(location=location) #defaults to   MEDIA_ROOT
        l=listdir(location)
        try:
            if request.FILES['cover_letter']:
                re_c = re.compile("cover_letter.*")
                redundant_cover = list(filter(re_c.match, l))
                for file in redundant_cover :
                    os.remove(os.path.join(location,file))
                cover_letter = request.FILES['cover_letter']
                filename_cover_letter = 'cover_letter'+str(request.user.id)+'.pdf'
                filename_c = fs.save(filename_cover_letter, cover_letter)
                student.cover_letter=fs.url(os.path.join('students',str(request.user.id),filename_c))
        except MultiValueDictKeyError as e:
            print(e)
        try:
            if request.FILES['resume']:
                re_r = re.compile("resume.*")
                redundant_resume = list(filter(re_r.match, l))
                for file in redundant_resume:
                    os.remove(os.path.join(location,file))
                resume = request.FILES['resume']
                filename_resume = 'resume'+str(request.user.id)+'.pdf'
                filename_r = fs.save(filename_resume, resume)
                student.resume=fs.url(os.path.join('students',str(request.user.id),filename_r))
        except MultiValueDictKeyError as e:
            print(e)

        l = listdir(location)
        re_c = re.compile("cover_letter_.*")
        re_r = re.compile("resume_.*")
        redundant_cover = list(filter(re_c.match, l))
        redundant_resume = list(filter(re_r.match, l))
        for file in redundant_cover + redundant_resume:
            os.remove(os.path.join(location,file))
        # code for saving cover letter & resume ends

        student.save()
        save_education(c_education_form,student)
        save_prev_education(request,student)
    else:
        messages.error(request, 'Error in updating profile')
    return student_form,c_education_form

        # skills = request.POST['skills_m']
        # if skills:
        #     skills = skills.split(',')
        #     for item in skills:
        #         s = Skill.objects.get(name=item)
        #         student.skills.add(s)
        # degree = request.POST['degree']
        # institute = request.POST['institute']
        # start_year = education_form.cleaned_data['start_year']
        # end_year = education_form.cleaned_data['end_year']
        # gpa = education_form.cleaned_data['gpa']
        # acad_discipline = education_form.cleaned_data['acad_discipline']
        # print(f"education_form.cleaned_data['acad_discipline'] ---------------- {education_form.cleaned_data['acad_discipline']}")
        # degree_obj = Degree.objects.get(id=degree)
        # acad_discipline_obj = Discipline.objects.get(id=acad_discipline)
        # try:
        #     print("1")
        #     e = Education.objects.filter(student=student)
        #     if e:
        #         print("1.2")
        #         education = e[0]
        #         education.degree = degree_obj
        #         education.institute = institute
        #         education.start_year = start_year
        #         education.end_year = end_year
        #         education.gpa = gpa
        #         education.save()
        #     else:
        #         education = Education(degree=degree_obj,institute=institute,start_year=start_year,end_year=end_year,gpa=gpa)
        #         education.save()
        #         student.education.add(education)
        # except IndexError as e:
        #     print("2")
        #     education = Education(degree=degree_obj,institute=institute,start_year=start_year,end_year=end_year,gpa=gpa)
        #     education.save()
        #     student.education.add(education)
        #     print(e)
        # except Exception as e:
        #     print("3")
        #     print(e)
        
        #education = Education(degree=degree_obj,institute=institute,start_year=start_year,end_year=end_year,gpa=gpa)
        # for i in range(1,6):
        #     try:
        #         degree = request.POST['degree_'+str(i)]
        #         institute = request.POST['institute_'+str(i)]
        #         start_year = request.POST['start_year_'+str(i)]
        #         end_year = request.POST['end_year_'+str(i)]
        #         gpa = request.POST['gpa_'+str(i)]
        #         add_education(student,degree,institute,start_year,end_year,gpa)
        #     except Exception as e:
        #         print(e)

        #education.save()
        #student.education.add(education)
        

def student_profile_confirm(request,pk,job):
    context = {}
    context['confirm']=True
    context['job_id']=job
    job_obj = Job.objects.get(id=job)
    context['job']=job_obj
    student = Student.objects.get(user=request.user)
    context['student']=student
    if request.method=='POST':
        student_form,education_form = save_student_profile(request,student)
    else:
        student_form = StudentForm(instance = student)
        education_form = EducationForm()
        jobApplicationForm = JobApplicationForm()
    context['form']=student_form
    context['education_form']=education_form
    context['jobApplicationForm']=jobApplicationForm
    context['scores'] = fetch_student_scores(student)
    context['projects'] = student.projects.all()
    return render(request,'emp/student_form.html',context)


def student_profile(request,pk):
    context = {}
    student = Student.objects.get(user=request.user)
    context['student']=student
    # context['skills']=Skill.objects.all()
    if request.method=='POST':
        print(1)
        student_form = StudentForm(request.POST)
        c_education_form = EducationForm(request.POST)
        print(2)
        if student_form.is_valid() and c_education_form.is_valid():
            print(3)
            student_form,education_form = save_student_profile(request,student)
            messages.success(request, 'Profile updated successfully')
        else:
            print(4)
            print("printing form errors -------------- ")
            print(student_form.errors)
            print("-------------- ")
            print(c_education_form.errors)
            print("done printing form errors -------------- ")
            messages.error(request, 'Error in updating profile')
    else:
        student_form = StudentForm(instance = student)
    try:
        edu = Education.objects.get(student=student,order=CURRENT_EDUCATION)
        context['current_edu']=edu
        c_education_form = EducationForm(instance=edu)
    except:
        c_education_form = EducationForm(initial={'order': CURRENT_EDUCATION})
    try:
        p_edu = Education.objects.get(student=student,order=PAST_EDUCATION)
        context['past_edu']=p_edu
    except:
        p_education_form = EducationForm(initial={'order': PAST_EDUCATION})
    
    context['form']=student_form
    context['education_form'] = c_education_form
    context['institutes'] = AcademicCenter.objects.values('id','institution_name')
    context['scores'] = fetch_student_scores(student)
    context['projects'] = student.projects.all()
    context['degrees'] = Degree.objects.all()
    context['acad_disciplines'] = Discipline.objects.all()
    context['CURRENT_EDUCATION'] = CURRENT_EDUCATION
    context['PAST_EDUCATION'] = PAST_EDUCATION
    return render(request,'emp/student_form.html',context)

def fetch_education_data(request):
    institutes = AcademicCenter.objects.all().values()
    degrees = Degree.objects.all().values()
    data = {}
    data['institutes']=list(institutes)
    data['degrees']=list(degrees)
    return JsonResponse(data)

def shortlist(request):
    data = {'msg':'success'}
    user_ids = request.GET.get('user_ids', None)
    job_id = int(request.GET.get('job_id', None))
    job = Job.objects.get(id=job_id)
    user_list = user_ids.split(',')
    l = []
    for item in user_list: 
        l.append(JobShortlist(job=job, spk_user_id=int(item),status=1))
    JobShortlist.objects.bulk_create(l)
    return JsonResponse(data) 

def shortlist_student(request):
    data = {'msg':'true'}
    students = request.GET.get('students', None)
    student_ids = [ int(x) for x in students[:-1].split(',') ]
    job_id = int(request.GET.get('job_id', None))
    job = Job.objects.get(id=job_id)
    try:
        # JobShortlist.objects.filter(job=job,student_id__in=student_ids).update(status=1)
        JobShortlist.objects.filter(job=job,spk_user__in=student_ids).update(status=1)
        data['updated']=True
        # data['students'] = User.objects.filter(student__id__in=student_ids).values('first_name','last_name')
    except:
        data['updated']=False
    return JsonResponse(data) 


def update_job_app_status(job,student,spk_user_id):
    job_shortlist = JobShortlist.objects.create(job=job,spk_user=spk_user_id,student=student,status=APPLIED)
    
# class JobShortlistListView(PermissionRequiredMixin,ListView):
class JobAppStatusListView(ListView):
    #permission_required = 'emp.view_job'
    template_name='emp/job_app_status_list.html'
    model = Job
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context
# def job_app_details(id):        
def job_app_details(request,id):
    context = {}
    job = Job.objects.get(id=id)
    students_awaiting = [x.student for x in JobShortlist.objects.filter(job_id=id) if x.status==0]
    students_awaiting1 = [x.student.spk_student_id for x in JobShortlist.objects.filter(job_id=id) if x.status==0]
    ta = TestAttendance.objects.filter(student_id__in=students_awaiting1)
    ta = ta.values('student_id','mdluser_id','mdlcourse_id','mdlquiz_id')
    ta_df=pd.DataFrame(ta)
    try:
        mdl_quiz_grades = MdlQuizGrades.objects.using('moodle').filter(userid__in=ta_df['mdluser_id'])
        mdl_quiz_grades=mdl_quiz_grades.values('quiz','userid','grade')
        mdl_quiz_grades_df=pd.DataFrame(mdl_quiz_grades)
        fossmdlcourses=FossMdlCourses.objects.filter(mdlquiz_id__in=mdl_quiz_grades_df['quiz']).values('mdlcourse_id','foss_id','mdlquiz_id')
        fossmdlcourses_df=pd.DataFrame(fossmdlcourses)
        fosscategory=FossCategory.objects.filter(id__in=fossmdlcourses_df['foss_id']).values('id','foss')
        fosscategory_df=pd.DataFrame(fosscategory)
        df1 = pd.merge(fossmdlcourses_df,fosscategory_df,left_on='foss_id',right_on='id')
        df1=df1.drop(['id','foss_id'], axis = 1)
        pd.merge(fossmdlcourses_df,fosscategory_df,left_on='foss_id',right_on='id')
        df1 = pd.merge(fossmdlcourses_df,fosscategory_df,left_on='foss_id',right_on='id')
        df1=df1.drop(['id','foss_id'], axis = 1)
        d = pd.merge(ta_df,mdl_quiz_grades_df,left_on=['mdlquiz_id','mdluser_id'],right_on=['quiz','userid'])
        df = pd.merge(d,df1,on='mdlcourse_id')
        sq = Student.objects.filter(spk_student_id__in=df['student_id'])
        sq = sq.values('spk_usr_id','address','spk_institute','gender','state','city','spk_student_id')
        sq_df=pd.DataFrame(sq)
        # users = User.objects.filter(student__in=sq).values('first_name','last_name')
        # users_df = pd.DataFrame(users)
        # sq_df=sq_df.join(users_df,on='user_id')
        # sq_df['fullname']=sq_df['first_name'] + sq_df['last_name']
        df=pd.merge(df,sq_df,left_on='student_id',right_on='spk_student_id')
        df1=df.drop_duplicates().pivot(index='student_id',columns='foss',values='grade')
        context['columns']=df1.columns
        df1.reset_index(inplace=True)
        dnew=pd.merge(df1,sq_df,left_on='student_id',right_on='spk_student_id').drop(columns= ['spk_student_id'])
        cols = list(dnew.columns.values)
        cols.remove('spk_usr_id')
        cols[0]='spk_usr_id'
        dnew=dnew[cols]
        dnew.set_index('spk_usr_id', inplace=True)
        json_records = dnew.reset_index().to_json(orient ='records')
        data = []
        data = json.loads(json_records)
        context = {'d': data}
    except:
        pass
    
    # context['df']=df1.to_html()
    students_shortlisted = [x.student for x in JobShortlist.objects.filter(job_id=id) if x.status==1]
    context['job'] = job
    context['students_awaiting'] = students_awaiting
    context['students_shortlisted'] = students_shortlisted
    context['mass_mail']=settings.MASS_MAIL
    return render(request,'emp/job_app_status_detail.html',context)


class JobShortlistDetailView(DetailView):
    model = JobShortlist
    template_name='emp/job_app_status_detail.html'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = Job.objects.get(id=self.kwargs['slug'])
        context['job']=job
        return context

class JobShortlistListView(ListView):
    model = JobShortlist
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

def add_student_job_status(request):
    context={}
    form = JobApplicationForm(request.POST)
    if form.is_valid():
        job_id = form.cleaned_data['job_id']
        spk_user_id = form.cleaned_data['spk_user_id']
        student_id = form.cleaned_data['student']
        student = Student.objects.get(id=student_id)
        job = Job.objects.get(id=job_id)
        r=update_job_app_status(job,student,spk_user_id)
        messages.success(request, 'Job Application Submitted Successfully!')
        context['applied_jobs'] = [x.job for x in JobShortlist.objects.filter(student=student)]
    else:
        print(form.errors)
    return HttpResponseRedirect(reverse('student_jobs'))

def check_student_eligibilty(request):
    flag = False
    spk_user_id = int(request.GET.get('spk_user_id'))
    job_id = int(request.GET.get('job_id'))
    data = {}
    spk_user = SpokenUser.objects.get(id=spk_user_id)     
    student = SpokenStudent.objects.get(user=spk_user)    
    job_id=job_id   
    
    job = Job.objects.get(id=job_id)   #get Job object
    state = list(map(lambda x : int(x),job.state.split(',')))
    city = list(map(lambda x : int(x),job.city.split(',')))
    institution_type = list(map(lambda x : int(x),job.institute_type.split(',')))
    activation_status = job.activation_status
    grade = job.grade
    foss_list = list(map(lambda x : int(x),job.foss.split(',')))
    #get quiz_list for all above fosses
    filter_quiz_ids = []
    for foss in foss_list:
        try:
            quiz = FossMdlCourses.objects.get(foss=foss).mdlquiz_id
            filter_quiz_ids.append(quiz)
        except FossMdlCourses.DoesNotExist as e:
            print(e)
    try:
        ta = TestAttendance.objects.values('mdluser_id','mdlcourse_id','mdlquiz_id').filter(student=student,mdlquiz_id__in=filter_quiz_ids,status__gte=3)
        ta_quiz_ids = [ x['mdlquiz_id'] for x in ta]
        if(set(filter_quiz_ids))==set(ta_quiz_ids):
            #check grade criteria
            mdl_user_id = TestAttendance.objects.filter(student=student)[0].mdluser_id
            mdl_quiz_grades = MdlQuizGrades.objects.using('moodle').filter(userid=mdl_user_id,grade__gte=grade,quiz__in=filter_quiz_ids)
            mdl_quiz_grades_ids = [ x.quiz for x in mdl_quiz_grades]
            if(sorted(set(mdl_quiz_grades_ids))==sorted(set(filter_quiz_ids))):
                #check other remaining criteria
                test_attendance=TestAttendance.objects.filter(
                        student=student,
                        mdlquiz_id__in=filter_quiz_ids,
                        test__academic__state__in=state if state else SpokenState.objects.using('spk').all(),
                        test__academic__city__in=city if city else SpokenCity.objects.using('spk').all(), 
                        test__academic__institution_type__in=institution_type if institution_type else InstituteType.objects.using('spk').all(), 
                        test__academic__status__in=[activation_status] if activation_status else [1,3]
                        )
                ta_quizes = [ ta.mdlquiz_id for ta in test_attendance]
                if(sorted(set(ta_quizes))==sorted(set(filter_quiz_ids))):
                    flag = True
                    data['is_eligible'] = flag
                    return JsonResponse(data)

    except IndexError as e:
        print(e)

    flag = True     #Temp keep
    data['is_eligible'] = flag 
    return JsonResponse(data)

@csrf_exempt
def ajax_state_city(request):
    if request.method == 'POST':
        data = {}
        state = request.POST.get('state')
        cities = SpokenCity.objects.filter(state=state).order_by('name')
        tmp = '<option value = None> --------- </option>'
        if cities:
            for i in cities:
                tmp +='<option value='+str(i.id)+'>'+i.name+'</option>'
        data['cities']=tmp
        return JsonResponse(data)

def student_profile_details(request,id,job):
    context = {}
    context['spk_student_id']=id
    context['job_id']=job
    job_obj = Job.objects.get(id=job)
    context['job']=job_obj
    # student = Student.objects.get(spk_student_id=id)
    student = Student.objects.get(spk_usr_id=id)
    context['student']=student
    context['MEDIA_URL']=settings.MEDIA_URL
    context['scores']=fetch_student_scores(student)
    return render(request,'emp/student_profile.html',context)

def student_jobs(request):
    context = {}
    #get applied jobs
    rec_student = Student.objects.get(user=request.user)
    applied_jobs = get_applied_joblist(rec_student.spk_usr_id)
    rec_jobs = get_recommended_jobs(rec_student)
    #get recommended jobs
    context['applied_jobs']=applied_jobs
    context['rec_jobs']=rec_jobs
    
    return render(request,'emp/student_jobs.html',context)

def error_404(request,exception):
    data = {}
    return render(request,'emp/error_404.html', data)

def error_500(request,exception):
    data = {}
    return render(request,'emp/error_500.html', data)



