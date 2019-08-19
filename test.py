from mindsdb import Predictor
import sys


mdb = Predictor(name='sensor123')

mdb.learn(to_predict='output',from_data="https://mindsdb-example-data.s3.eu-west-2.amazonaws.com/sensor_data.csv",use_gpu=True,stop_training_in_x_seconds=40)

p_arr = mdb.predict(when_data='https://mindsdb-example-data.s3.eu-west-2.amazonaws.com/sensor_data.csv')

pdct = mdb.predict(when={'sensor 1': 0.5, 'sensor 2': 2, 'sensor 3': 0, 'sensor4': 5})
print(pdct)

for p in p_arr:
    exp_s = p.epitomize()
    exp = p.explain()

    if len(exp['output']) > 0:
        print(exp)
        print(exp_s)

'''

predictions = mdb.predict(...etc)
for p in predictions:
    print(p.simple())

    p.explain()['target_variable'][0]['value_range']

# Interface:

predictions = mindsdb.predict(blah)

prediction = predictions[12]

.value

prediction.explain() -->
{
    'rental_price':
        [
            {
                'value': 4656.221332754563,
                'value_range': [4303.627029776876, 4656.221332754563],
                'confidence': 0.9692603046355561,
                'explaination': "\n\n*A similar value for the predicted column rental_price occurs rarely in your dataset, it is partially because of this reason that we aren't confident this prediction is correct.\n\n*The value of the column number_of_rooms played a large role in generating this prediction.\n\n*The value of the column sqft played a large role in generating this prediction.\n\n*The value of the column initial_price played a large role in generating this prediction.\n\n*The column location is probably not very relevant for this prediction.\n\n*The column neighborhood is probably not very relevant for this prediction.",
                'simple': 'We are 97% confident your answer lies between 4304 and 4656'
            }
        ]
    }


prediction.simple() --> 'We are 54% confident your answer lies between 1706 and 1799.' OR 'We are 85% confident your answer is "The image represents and apple".'
'''
