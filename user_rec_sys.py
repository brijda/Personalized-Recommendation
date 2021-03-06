import pandas as pd
import numpy as np
import keras
import keras.models as kmodels
import keras.layers as klayers
import keras.backend as K
from keras.optimizers import Adam
from gensim.models import Word2Vec
from keras.layers import Dense,LSTM
from keras.models import Sequential
from tensorflow import set_random_seed
from keras.models import load_model
from keras.utils import plot_model
warnings.filterwarnings('ignore')
np.random.seed(123)

#Read data into pandas dataframe
df=pd.read_csv('./beauty_df.csv',header='infer')
df=df[['reviewerID', 'asin','overall','reviewTime']]

#Rename the columns
df.columns=['userid', 'item_id', 'rating', 'reviewTime']
df=df.sort_values(['reviewTime'],ascending=[True])

#Divide the train and test data

length=int(0.75*len(df))
train_data=df[:length]
test_data=df[length:]
print(train_data.shape, test_data.shape)
train_data = train_data.reset_index()
test_data = test_data.reset_index()
    
#find item sequences by user in train and test
item_seq_train=train_data.groupby("userid")['item_id'].apply(list).values
item_seq_test=test_data.groupby("userid")['item_id'].apply(list).values

#Create a dictionary where key is user and value is the items purchased by user in sequence
def user_grouping(df):
    user_seq=defaultdict(list)
    user_grp=df.groupby(df['userid']).groups
    df=np.array(df)
    for key, value in user_grp.items():
         temp = value
         val=df[temp,]
         val=val.tolist()
         user_seq[key].append(val)
    
    for key,value in user_seq.items():
         for i in range(0,len(value)):
             for j in range(0,len(value[i])):
                 value[i][j]=str(value[i][j][2])
         for i in range(0,len(value)):
             if len(value[i])<6:
                 w=6-len(value[i])
                 value[i]=['padding_id']*w+value[i]
    return user_seq
    
#find train and test user dictionaries
user_train_seq=user_grouping(train_data)
user_test_seq=user_grouping(train_data)

# We consider the minimum sequence length as 6. If length is less than 6, we append dummy ids to the sequence  
def min_six_len_seq(dictList):
    new_list=[]
    for i in range(0,len(dictList)):
        if len(dictList[i])<6:
            w=6-len(dictList[i])
            dictList[i]=['padding_id']*w+dictList[i]
    return dictList

#find the train and test sequences of min len 6
item_train = min_six_len_seq(item_seq_train)
item_test = min_six_len_seq(item_seq_test)

# train word2vec model on train_data to get item embeddings
def word2vec_model(train_data):
    model = Word2Vec(train_data,size=50,window = 3,min_count =1,iter=20)
    return model


#train the model and save
wv_model=word2vec_model(item_train)
wv_model.save('word2vec_model')

#find full vocabulary
entire_products=[]
for key,value in model.wv.vocab.items():
    entire_products.append(key)
np.save('./entire_products.npy',entire_products)

# Divide the sequences into length of 6. ( First 5 items are for train, 6th one for target)
# Also, attach each sequence with corresponding user embedding and store it.

#User embedding obtained from neural factorization
with open('./user_embed','rb') as f:
    user_embed=cPickle.load(f)
    

def input_sequences(new_list, win_size=5,user_item):
    input_seq=[]
    target=[]
    user_input=[]
    #For new users
    unknown_id=np.random.random((50,))
    for i in range(0,len(new_list)):
        seq_len = len(new_list[i])
        
        #finding user for this sequence
        for key,value in user_item.items():
             if [new_listy[i]]==value:
                 user=key
        for j in range(0,seq_len):
            if j+win_size<seq_len:
                if new_list[i][j+5] in entire_products:
                    try:
                        input_seq.append(new_list[i][j:j+5])
                        target.append(new_list[i][j+5])
                        user_input.append(user_emb[user])
                    except KeyError:
                        print("new")
                        user_input.append(unknown_id)

    return input_seq,target,user_input


# Encoding the target.If new item arrives which i
def num_products(target):
    product_label=LabelEncoder()
    product_label.fit(entire_products)
    target_int = product_label.transform(target)
    return target_int
    
#Create Train and test input and target sequences
train_x,target_train,user_train=input_sequences(item_seq_train,user_train_seq)
train_y=num_products(target_train)

test_x,target_test,user_test=input_sequences(item_seq_test,user_test_seq)
test_y=num_products(target_test)
    
#represent each item with prod2vec embedding and if new item comes in test set, represent it with unknown id
unknown_item_id=np.random.random((50,))
def w2v_data_extraction(new_list):
    w2v_data=[]
    for i in range(0,len(new_list)):
        seq_vec=[]
        for j in range(0,len(new_list[i])):
            try:
                embedding=wv_model.wv[new_list[i][j]]
            except KeyError:
                embedding=unknown_item_id
            seq_vec.append(embedding)
                
        w2v_data.append(seq_vec)
    return np.asarray(w2v_data)

train_x_emb=w2v_data_extraction(train_x)
test_x_emb=w2v_data_extraction(test_x)

#model architecture
# Model architecture
def model_arch():
    main_input = Input(shape=(5,50), name='main_input')
    lstm_out = LSTM(32)(main_input)
    auxiliary_input = Input(shape=(50,), name='aux_input')
    merge_in = keras.layers.concatenate([lstm_out, auxiliary_input])
    #We stack a deep densely-connected network on top
    merge_in = Dense(64, activation='relu')(merge_in)
    main_output = Dense(total_vocab, activation='softmax', name='main_output')(merge_in)
    model = Model(inputs=[main_input, auxiliary_input], outputs=main_output)
    model.compile(loss='categorical_crossentropy',metrics=['accuracy'],optimizer='ADAM')
    return model

#represent output as one-hot encoded
def one_hot(seq,total_vocab):
    seq_one_hot=np.zeros([len(seq),total_vocab])
    for i in range(0,len(seq)):
        seq_one_hot[i][seq[i]]=1
    return seq_one_hot

#fit the data
def model_fit(model,train_x,train_u,train_seq,total_vocab):
    train_y=one_hot(train_seq,total_vocab)
    print("model is building")
    model.fit(batch_size=64,epochs=10,x=[train_x,train_u],y=train_y)
    print("model building done")
    model.save('keras_model.h5')
    eturn model

total_vocab=12102
model = model_arch()
model=model_fit(model,train_x_emb,user_train,train_y,total_vocab)

# Hit rate at 1 on test data
def hit_rate_at_1(prediction,actual):
    return accuracy_score(prediction,actual)


# Hit rata at 5 on test data
def hit_rate_at_5(pred,actual):
    predics = []
    for i in range(0, len(pred)):
        predics.append(np.argsort(pred[i])[-5:])
    count = 0
    for i in range(0, len(predics)):
        if actual[i] in predics[i]:
            count = count + 1

    return count/len(actual)


# Hit rate at 10 on test data
def hit_rate_at_10(pred, actual):
    predics = []
    for i in range(0, len(pred)):
        predics.append(np.argsort(pred[i])[-10:])
    count = 0
    for i in range(0, len(predics)):
        if actual[i] in predics[i]:
            count = count + 1
    return count /len(actual)
    
# Prediction on test data
def model_predict(model,test_x,test_u,test_seq):
    pred=model.predict(x=[test_x,test_u])
    preddy=np.argmax(a=pred,axis=1)
    print(hit_rate_at_1(preddy,test_seq))
    print(hit_rate_at_5(pred, test_seq))
    print(hit_rate_at_10(pred, test_seq))

 
model_predict(model,test_x_emb,user_test,test_y)


    
    
    
